'use strict';

const db = require('../db');
const redis = require('../redis');
const winrm = require('../winrm');
const { getHostConnection } = require('./accountCreation');

/**
 * Configure WinRM on a remote host
 * @param {number} hostId - hosts.id
 * @param {string} certThumbprint - Certificate thumbprint for HTTPS listener
 * @param {number} operatorId - User ID performing the operation
 * @returns {object} Result
 */
async function configureWinrmOnHost(hostId, certThumbprint, operatorId) {
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [hostId]);
  if (!hostRow) {
    throw new Error(`Host ${hostId} not found`);
  }

  const hostConn = getHostConnection(hostRow);

  // Create async task record
  const asyncTask = await db.insert('async_tasks', {
    task_id: `configure-winrm-${hostId}-${Date.now()}`,
    name: `Configure WinRM on ${hostRow.name}`,
    status: 'running',
    created_by_id: operatorId,
    started_at: new Date().toISOString(),
    target_object_id: hostId,
    target_content_type: 'host',
  });

  try {
    await redis.updateTaskProgress(asyncTask.task_id, { percent: 10, message: 'Configuring WinRM service' });

    const escapedThumbprint = winrm.escapePowerShell(certThumbprint || '');

    // Configure WinRM script
    let script = `
$ErrorActionPreference = 'Stop'

# Ensure WinRM service is running
Set-Service -Name WinRM -StartupType Automatic
Start-Service -Name WinRM -ErrorAction SilentlyContinue

# Configure WinRM settings
winrm set winrm/config/service '@{AllowUnencrypted="true"}'
winrm set winrm/config/service '@{MaxConcurrentOperationsPerUser="1500"}'
winrm set winrm/config/winrs '@{MaxMemoryPerShellMB="1024"}'
winrm set winrm/config '@{MaxTimeoutms="1800000"}'

# Enable CredSSP
Enable-WSManCredSSP -Role Server -Force

# Configure firewall for WinRM
$firewallRule = Get-NetFirewallRule -Name "WINRM-HTTP-In-TCP-PUBLIC" -ErrorAction SilentlyContinue
if (-not $firewallRule) {
    New-NetFirewallRule -Name "WINRM-HTTP-In-TCP-PUBLIC" -DisplayName "Windows Remote Management (HTTP-In)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5985
}
`;

    if (escapedThumbprint) {
      script += `
# Configure HTTPS listener
$existingListener = Get-WSManInstance -ResourceURI winrm/config/Listener -Enumerate | Where-Object { $_.Transport -eq 'HTTPS' }
if ($existingListener) {
    Remove-WSManInstance -ResourceURI winrm/config/Listener -SelectorSet @{Transport='HTTPS';Address='*'}
}

New-WSManInstance -ResourceURI winrm/config/Listener -SelectorSet @{Transport='HTTPS';Address='*'} -ValueSet @{Hostname='${winrm.escapePowerShell(hostRow.hostname)}';CertificateThumbprint='${escapedThumbprint}'}

# Configure firewall for WinRM HTTPS
$httpsRule = Get-NetFirewallRule -Name "WINRM-HTTPS-In-TCP-PUBLIC" -ErrorAction SilentlyContinue
if (-not $httpsRule) {
    New-NetFirewallRule -Name "WINRM-HTTPS-In-TCP-PUBLIC" -DisplayName "Windows Remote Management (HTTPS-In)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5986
}
`;
    }

    script += `
# Restart WinRM service
Restart-Service -Name WinRM -Force
Write-Output "WinRM configured successfully"
`;

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 50, message: 'Executing WinRM configuration' });

    const result = await winrm.executePowershell(hostConn, script);

    if (result.exitCode !== 0) {
      throw new Error(`WinRM configuration failed: ${result.stderr}`);
    }

    // Update host status
    await db.update('hosts', {
      status: 'online',
      cert_provision_status: 'configured',
    }, 'id = $1', [hostId]);

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 100, message: 'WinRM configured successfully' });

    // Update async task
    await db.update('async_tasks', {
      status: 'completed',
      completed_at: new Date().toISOString(),
      progress: 100,
      result: JSON.stringify({ exitCode: result.exitCode, stdout: result.stdout.substring(0, 500) }),
    }, 'id = $1', [asyncTask.id]);

    return { hostId, message: 'WinRM configured successfully' };
  } catch (err) {
    await db.update('async_tasks', {
      status: 'failed',
      completed_at: new Date().toISOString(),
      error_message: err.message,
    }, 'id = $1', [asyncTask.id]);

    await db.update('hosts', { status: 'error' }, 'id = $1', [hostId]);

    throw err;
  }
}

/**
 * Test WinRM connection to a host and update status
 * @param {number} hostId - hosts.id
 * @returns {object} Result
 */
async function testWinrmConnection(hostId) {
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [hostId]);
  if (!hostRow) {
    throw new Error(`Host ${hostId} not found`);
  }

  const hostConn = getHostConnection(hostRow);

  try {
    const result = await winrm.executePowershell(hostConn, 'Write-Output "CONNECTION_OK"');

    if (result.exitCode === 0 && result.stdout.trim() === 'CONNECTION_OK') {
      await db.update('hosts', { status: 'online' }, 'id = $1', [hostId]);
      return { hostId, status: 'online', message: 'Connection successful' };
    } else {
      await db.update('hosts', { status: 'error' }, 'id = $1', [hostId]);
      return { hostId, status: 'error', message: `Connection failed: ${result.stderr}` };
    }
  } catch (err) {
    await db.update('hosts', { status: 'offline' }, 'id = $1', [hostId]);
    return { hostId, status: 'offline', message: `Connection error: ${err.message}` };
  }
}

/**
 * Test WinRM connection with raw parameters (no DB lookup)
 * @param {string} connectionType - Connection type (winrm)
 * @param {string} hostname - Host address
 * @param {number} port - Port number
 * @param {boolean} useSsl - Use SSL
 * @param {string} authMethod - Authentication method (ntlm/certificate)
 * @param {string} username - Username
 * @param {string} password - Password
 * @returns {object} Result
 */
async function testWinrmConnectionRaw(connectionType, hostname, port, useSsl, authMethod, username, password) {
  const hostConn = {
    hostname,
    port: port || (useSsl ? 5986 : 5985),
    useSsl: useSsl || false,
    authMethod: authMethod || 'ntlm',
    username: username || '',
    password: password || '',
  };

  try {
    const result = await winrm.executePowershell(hostConn, 'Write-Output "CONNECTION_OK"');

    if (result.exitCode === 0 && result.stdout.trim() === 'CONNECTION_OK') {
      return { success: true, message: 'Connection successful' };
    } else {
      return { success: false, message: `Connection failed: ${result.stderr}` };
    }
  } catch (err) {
    return { success: false, message: `Connection error: ${err.message}` };
  }
}

/**
 * Install certificates on a remote host
 * @param {number} hostId - hosts.id
 * @param {string} certPem - Certificate PEM content
 * @param {string} certFilename - Certificate filename
 * @param {number} operatorId - User ID performing the operation
 * @returns {object} Result
 */
async function installCertificatesOnHost(hostId, certPem, certFilename, operatorId) {
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [hostId]);
  if (!hostRow) {
    throw new Error(`Host ${hostId} not found`);
  }

  const hostConn = getHostConnection(hostRow);

  // Create async task record
  const asyncTask = await db.insert('async_tasks', {
    task_id: `install-certs-${hostId}-${Date.now()}`,
    name: `Install certificates on ${hostRow.name}`,
    status: 'running',
    created_by_id: operatorId,
    started_at: new Date().toISOString(),
    target_object_id: hostId,
    target_content_type: 'host',
  });

  try {
    await redis.updateTaskProgress(asyncTask.task_id, { percent: 10, message: 'Installing certificates' });

    // Base64 encode the cert to safely pass through PowerShell
    const certBase64 = Buffer.from(certPem).toString('base64');
    const escapedFilename = winrm.escapePowerShell(certFilename || 'cert.pem');

    const script = `
$ErrorActionPreference = 'Stop'
$certB64 = '${certBase64}'
$certBytes = [System.Convert]::FromBase64String($certB64)
$certPath = "$env:TEMP\\${escapedFilename}"
[System.IO.File]::WriteAllBytes($certPath, $certBytes)

# Import certificate to LocalMachine Root store
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certPath)
$store = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
$store.Open('ReadWrite')
$store.Add($cert)
$store.Close()

# Also add to TrustedPeople store
$store2 = New-Object System.Security.Cryptography.X509Certificates.X509Store('TrustedPeople', 'LocalMachine')
$store2.Open('ReadWrite')
$store2.Add($cert)
$store2.Close()

# Cleanup temp file
Remove-Item $certPath -Force

Write-Output "Certificate installed successfully. Thumbprint: $($cert.Thumbprint)"
`;

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 50, message: 'Executing certificate installation' });

    const result = await winrm.executePowershell(hostConn, script);

    if (result.exitCode !== 0) {
      throw new Error(`Certificate installation failed: ${result.stderr}`);
    }

    // Extract thumbprint from output
    const thumbprintMatch = result.stdout.match(/Thumbprint:\s*([A-Fa-f0-9]+)/);
    const thumbprint = thumbprintMatch ? thumbprintMatch[1] : '';

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 100, message: 'Certificates installed successfully' });

    // Update async task
    await db.update('async_tasks', {
      status: 'completed',
      completed_at: new Date().toISOString(),
      progress: 100,
      result: JSON.stringify({ thumbprint, stdout: result.stdout.substring(0, 500) }),
    }, 'id = $1', [asyncTask.id]);

    return { hostId, thumbprint, message: 'Certificates installed successfully' };
  } catch (err) {
    await db.update('async_tasks', {
      status: 'failed',
      completed_at: new Date().toISOString(),
      error_message: err.message,
    }, 'id = $1', [asyncTask.id]);

    throw err;
  }
}

// Task handler mapping
const handlers = {
  configure_winrm_on_host: (task) => configureWinrmOnHost(
    task.payload.hostId,
    task.payload.certThumbprint,
    task.payload.operatorId
  ),
  test_winrm_connection: (task) => testWinrmConnection(task.payload.hostId),
  test_winrm_connection_raw: (task) => testWinrmConnectionRaw(
    task.payload.connectionType,
    task.payload.hostname,
    task.payload.port,
    task.payload.useSsl,
    task.payload.authMethod,
    task.payload.username,
    task.payload.password
  ),
  install_certificates_on_host: (task) => installCertificatesOnHost(
    task.payload.hostId,
    task.payload.certPem,
    task.payload.certFilename,
    task.payload.operatorId
  ),
};

module.exports = {
  configureWinrmOnHost,
  testWinrmConnection,
  testWinrmConnectionRaw,
  installCertificatesOnHost,
  handlers,
};
