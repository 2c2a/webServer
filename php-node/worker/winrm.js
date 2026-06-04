'use strict';

const http = require('http');
const https = require('https');
const crypto = require('crypto');
const fs = require('fs');

const WINRM_CONTENT_TYPE = 'application/soap+xml';
const WINRM_NS = 'http://schemas.microsoft.com/wbem/wsman/1';
const WINRM_NS_S = 'http://www.w3.org/2003/05/soap-envelope';
const WINRM_NS_WSMID = 'http://schemas.dmtf.org/wbem/wsman/identity/1/wsmanidentity.xsd';

const DEFAULT_TIMEOUT = 30000;
const MAX_ENVELOPE_SIZE = 153600;

/**
 * Escape a string for use in PowerShell
 * @param {string} str - String to escape
 * @returns {string} Escaped string
 */
function escapePowerShell(str) {
  if (typeof str !== 'string') return String(str);
  return str
    .replace(/'/g, "''")
    .replace(/\0/g, '');
}

/**
 * Generate a UUID for WinRM messages
 * @returns {string}
 */
function generateUUID() {
  return crypto.randomUUID();
}

/**
 * Build NTLM Type 1 message
 * @returns {string} Base64 encoded NTLM Type 1 message
 */
function buildNTLMType1() {
  const signature = Buffer.from('NTLMSSP\0', 'ascii');
  const type = Buffer.alloc(4);
  type.writeUInt32LE(1, 0);
  const flags = Buffer.alloc(4);
  flags.writeUInt32LE(0x000b2006, 0); // NTLMSSP_NEGOTIATE_NTLM | NTLMSSP_NEGOTIATE_UNICODE | etc.
  const domainLen = Buffer.alloc(2);
  const domainMaxLen = Buffer.alloc(2);
  const domainOffset = Buffer.alloc(4);
  const workstationLen = Buffer.alloc(2);
  const workstationMaxLen = Buffer.alloc(2);
  const workstationOffset = Buffer.alloc(4);

  return Buffer.concat([
    signature, type, flags,
    domainLen, domainMaxLen, domainOffset,
    workstationLen, workstationMaxLen, workstationOffset,
  ]).toString('base64');
}

/**
 * Build NTLM Type 3 message (simplified)
 * @param {string} username
 * @param {string} password
 * @param {Buffer} serverChallenge - Type 2 message from server
 * @returns {string} Base64 encoded NTLM Type 3 message
 */
function buildNTLMType3(username, password, type2Msg) {
  const passwordBuf = Buffer.from(password, 'utf16le');
  const ntHash = crypto.createHash('md4').update(passwordBuf).digest();

  // Parse Type 2 challenge
  const serverNonce = type2Msg.slice(24, 32);

  // NTLMv2 response
  const temp = Buffer.concat([
    serverNonce,
    Buffer.from(generateUUID().replace(/-/g, ''), 'hex').slice(0, 8),
  ]);

  const hmacMd5 = crypto.createHmac('md5', ntHash);
  hmacMd5.update(temp);
  const ntProofStr = hmacMd5.digest();

  const usernameBuf = Buffer.from(username, 'utf16le');
  const workstationBuf = Buffer.from('', 'utf16le');

  const signature = Buffer.from('NTLMSSP\0', 'ascii');
  const type = Buffer.alloc(4);
  type.writeUInt32LE(3, 0);

  const lmLen = Buffer.alloc(2);
  lmLen.writeUInt16LE(0, 0);
  const lmMaxLen = Buffer.alloc(2);
  lmMaxLen.writeUInt16LE(0, 0);
  const lmOffset = Buffer.alloc(4);
  lmOffset.writeUInt32LE(64 + usernameBuf.length + workstationBuf.length, 0);

  const ntLen = Buffer.alloc(2);
  ntLen.writeUInt16LE(ntProofStr.length, 0);
  const ntMaxLen = Buffer.alloc(2);
  ntMaxLen.writeUInt16LE(ntProofStr.length, 0);
  const ntOffset = Buffer.alloc(4);
  ntOffset.writeUInt32LE(64 + usernameBuf.length + workstationBuf.length, 0);

  const domainLen = Buffer.alloc(2);
  domainLen.writeUInt16LE(0, 0);
  const domainMaxLen = Buffer.alloc(2);
  domainMaxLen.writeUInt16LE(0, 0);
  const domainOffset = Buffer.alloc(4);
  domainOffset.writeUInt32LE(64, 0);

  const userLen = Buffer.alloc(2);
  userLen.writeUInt16LE(usernameBuf.length, 0);
  const userMaxLen = Buffer.alloc(2);
  userMaxLen.writeUInt16LE(usernameBuf.length, 0);
  const userOffset = Buffer.alloc(4);
  userOffset.writeUInt32LE(64, 0);

  const wsLen = Buffer.alloc(2);
  wsLen.writeUInt16LE(workstationBuf.length, 0);
  const wsMaxLen = Buffer.alloc(2);
  wsMaxLen.writeUInt16LE(workstationBuf.length, 0);
  const wsOffset = Buffer.alloc(4);
  wsOffset.writeUInt32LE(64 + usernameBuf.length, 0);

  const sessionLen = Buffer.alloc(2);
  const sessionMaxLen = Buffer.alloc(2);
  const sessionOffset = Buffer.alloc(4);

  const flags = Buffer.alloc(4);
  flags.writeUInt32LE(0x00088215, 0);

  const msg = Buffer.concat([
    signature, type,
    lmLen, lmMaxLen, lmOffset,
    ntLen, ntMaxLen, ntOffset,
    domainLen, domainMaxLen, domainOffset,
    userLen, userMaxLen, userOffset,
    wsLen, wsMaxLen, wsOffset,
    sessionLen, sessionMaxLen, sessionOffset,
    flags,
    usernameBuf,
    workstationBuf,
    ntProofStr,
  ]);

  return msg.toString('base64');
}

/**
 * Build WinRM SOAP envelope for shell creation
 * @returns {string} SOAP XML
 */
function buildCreateShellEnvelope() {
  const uuid = generateUUID();
  return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="${WINRM_NS_S}" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsman="${WINRM_NS}" xmlns:shell="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">
  <s:Header>
    <wsa:Action>${WINRM_NS}/shell/action/Create</wsa:Action>
    <wsa:To>http://localhost:5985/wsman</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd</wsman:ResourceURI>
    <wsa:MessageID>uuid:${uuid}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsman:MaxEnvelopeSize s:mustUnderstand="true">${MAX_ENVELOPE_SIZE}</wsman:MaxEnvelopeSize>
    <wsman:Locale xml:lang="en-US" s:mustUnderstand="false"/>
    <s:MustUnderstand s:mustUnderstand="true">true</s:MustUnderstand>
  </s:Header>
  <s:Body>
    <shell:Shell>
      <shell:InputStreams>stdin</shell:InputStreams>
      <shell:OutputStreams>stdout stderr</shell:OutputStreams>
    </shell:Shell>
  </s:Body>
</s:Envelope>`;
}

/**
 * Build WinRM SOAP envelope for command execution
 * @param {string} shellId - Shell identifier
 * @param {string} command - Command to execute
 * @returns {string} SOAP XML
 */
function buildExecuteCommandEnvelope(shellId, command) {
  const uuid = generateUUID();
  const escapedCommand = command.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="${WINRM_NS_S}" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsman="${WINRM_NS}" xmlns:shell="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">
  <s:Header>
    <wsa:Action>http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Command</wsa:Action>
    <wsa:To>http://localhost:5985/wsman</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd</wsman:ResourceURI>
    <wsa:MessageID>uuid:${uuid}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsman:MaxEnvelopeSize s:mustUnderstand="true">${MAX_ENVELOPE_SIZE}</wsman:MaxEnvelopeSize>
    <wsman:Locale xml:lang="en-US" s:mustUnderstand="false"/>
    <shell:ShellId s:mustUnderstand="true">${shellId}</shell:ShellId>
  </s:Header>
  <s:Body>
    <shell:CommandLine>
      <shell:Command>${escapedCommand}</shell:Command>
    </shell:CommandLine>
  </s:Body>
</s:Envelope>`;
}

/**
 * Build WinRM SOAP envelope for receiving output
 * @param {string} shellId - Shell identifier
 * @param {string} commandId - Command identifier
 * @returns {string} SOAP XML
 */
function buildReceiveOutputEnvelope(shellId, commandId) {
  const uuid = generateUUID();
  return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="${WINRM_NS_S}" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsman="${WINRM_NS}" xmlns:shell="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">
  <s:Header>
    <wsa:Action>http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Receive</wsa:Action>
    <wsa:To>http://localhost:5985/wsman</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd</wsman:ResourceURI>
    <wsa:MessageID>uuid:${uuid}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <wsman:MaxEnvelopeSize s:mustUnderstand="true">${MAX_ENVELOPE_SIZE}</wsman:MaxEnvelopeSize>
    <wsman:Locale xml:lang="en-US" s:mustUnderstand="false"/>
    <shell:ShellId s:mustUnderstand="true">${shellId}</shell:ShellId>
  </s:Header>
  <s:Body>
    <shell:Receive>
      <shell:DesiredStream>stdout stderr</shell:DesiredStream>
      <shell:CommandId>${commandId}</shell:CommandId>
    </shell:Receive>
  </s:Body>
</s:Envelope>`;
}

/**
 * Build WinRM SOAP envelope for shell deletion
 * @param {string} shellId - Shell identifier
 * @returns {string} SOAP XML
 */
function buildDeleteShellEnvelope(shellId) {
  const uuid = generateUUID();
  return `<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="${WINRM_NS_S}" xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing"
  xmlns:wsman="${WINRM_NS}" xmlns:shell="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">
  <s:Header>
    <wsa:Action>${WINRM_NS}/shell/action/Delete</wsa:Action>
    <wsa:To>http://localhost:5985/wsman</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd</wsman:ResourceURI>
    <wsa:MessageID>uuid:${uuid}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address s:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
    <shell:ShellId s:mustUnderstand="true">${shellId}</shell:ShellId>
  </s:Header>
  <s:Body/>
</s:Envelope>`;
}

/**
 * Extract ShellId from Create response
 * @param {string} xml - SOAP response
 * @returns {string|null}
 */
function parseShellId(xml) {
  const match = xml.match(/<shell:ShellId[^>]*>([^<]+)<\/shell:ShellId>/);
  return match ? match[1] : null;
}

/**
 * Extract CommandId from Execute response
 * @param {string} xml - SOAP response
 * @returns {string|null}
 */
function parseCommandId(xml) {
  const match = xml.match(/<shell:CommandId[^>]*>([^<]+)<\/shell:CommandId>/);
  return match ? match[1] : null;
}

/**
 * Extract output from Receive response
 * @param {string} xml - SOAP response
 * @returns {{stdout: string, stderr: string, exitCode: number, done: boolean}}
 */
function parseOutput(xml) {
  let stdout = '';
  let stderr = '';
  let exitCode = -1;
  let done = false;

  // Extract stdout
  const stdoutMatches = xml.matchAll(/<stream:[^>]*Name="stdout"[^>]*>([^<]*)<\/stream:/g);
  for (const m of stdoutMatches) {
    if (m[1]) {
      try {
        stdout += Buffer.from(m[1], 'base64').toString('utf8');
      } catch (_) {
        stdout += m[1];
      }
    }
  }

  // Extract stderr
  const stderrMatches = xml.matchAll(/<stream:[^>]*Name="stderr"[^>]*>([^<]*)<\/stream:/g);
  for (const m of stderrMatches) {
    if (m[1]) {
      try {
        stderr += Buffer.from(m[1], 'base64').toString('utf8');
      } catch (_) {
        stderr += m[1];
      }
    }
  }

  // Check for exit code
  const exitMatch = xml.match(/<shell:ExitCode[^>]*>([^<]+)<\/shell:ExitCode>/);
  if (exitMatch) {
    exitCode = parseInt(exitMatch[1], 10);
    done = true;
  }

  // Check if command is done
  const doneMatch = xml.match(/<shell:CommandState[^>]*State="http:\/\/schemas\.microsoft\.com\/wbem\/wsman\/1\/windows\/shell\/CommandState\/Done"/);
  if (doneMatch) {
    done = true;
  }

  return { stdout, stderr, exitCode, done };
}

/**
 * Make an HTTP/HTTPS request
 * @param {object} options - Request options
 * @returns {Promise<{statusCode: number, headers: object, body: string}>}
 */
function httpRequest(options) {
  return new Promise((resolve, reject) => {
    const transport = options.useSsl ? https : http;
    const reqOpts = {
      hostname: options.hostname,
      port: options.port,
      path: options.path || '/wsman',
      method: 'POST',
      headers: {
        'Content-Type': `${WINRM_CONTENT_TYPE};charset=UTF-8`,
        'Content-Length': Buffer.byteLength(options.body),
      },
      timeout: options.timeout || DEFAULT_TIMEOUT,
      rejectUnauthorized: false,
    };

    // Add auth header
    if (options.authHeader) {
      reqOpts.headers['Authorization'] = options.authHeader;
    }

    // Add client certificate
    if (options.cert && options.key) {
      reqOpts.cert = options.cert;
      reqOpts.key = options.key;
    }

    const req = transport.request(reqOpts, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: Buffer.concat(chunks).toString('utf8'),
        });
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('HTTP request timed out'));
    });

    req.write(options.body);
    req.end();
  });
}

/**
 * Perform NTLM authentication handshake
 * @param {object} host - Host connection info
 * @param {string} soapBody - SOAP envelope
 * @returns {Promise<{statusCode: number, body: string}>}
 */
async function ntlmAuthRequest(host, soapBody) {
  const options = {
    hostname: host.hostname,
    port: host.port || 5985,
    useSsl: host.useSsl || false,
    timeout: DEFAULT_TIMEOUT,
    body: soapBody,
  };

  // Step 1: Send Type 1
  const type1Header = `Negotiate ${buildNTLMType1()}`;
  options.authHeader = type1Header;
  const res1 = await httpRequest(options);

  if (res1.statusCode !== 401) {
    throw new Error(`NTLM auth failed: expected 401, got ${res1.statusCode}`);
  }

  // Extract Type 2 from response
  const authHeader = res1.headers['www-authenticate'] || '';
  const ntlmMatch = authHeader.match(/NTLM\s+([A-Za-z0-9+/=]+)/);
  if (!ntlmMatch) {
    throw new Error('NTLM auth failed: no Type 2 message in response');
  }
  const type2Buf = Buffer.from(ntlmMatch[1], 'base64');

  // Step 2: Send Type 3 with actual request
  const type3Header = `Negotiate ${buildNTLMType3(host.username, host.password, type2Buf)}`;
  options.authHeader = type3Header;
  options.body = soapBody;
  const res2 = await httpRequest(options);

  return res2;
}

/**
 * Perform certificate-based authentication
 * @param {object} host - Host connection info
 * @param {string} soapBody - SOAP envelope
 * @returns {Promise<{statusCode: number, body: string}>}
 */
async function certAuthRequest(host, soapBody) {
  let cert = null;
  let key = null;

  if (host.certPemPath) {
    cert = fs.readFileSync(host.certPemPath);
  }
  if (host.certKeyPath) {
    key = fs.readFileSync(host.certKeyPath);
  }

  const options = {
    hostname: host.hostname,
    port: host.port || 5986,
    useSsl: true,
    timeout: DEFAULT_TIMEOUT,
    body: soapBody,
    cert,
    key,
  };

  return httpRequest(options);
}

/**
 * Send a SOAP request to WinRM
 * @param {object} host - Host connection info
 * @param {string} soapBody - SOAP envelope
 * @returns {Promise<{statusCode: number, body: string}>}
 */
async function sendWinrmRequest(host, soapBody) {
  if (host.authMethod === 'certificate') {
    return certAuthRequest(host, soapBody);
  }
  return ntlmAuthRequest(host, soapBody);
}

/**
 * Send a request via Gateway API (for tunnel hosts)
 * @param {object} host - Host info with tunnel_token
 * @param {string} soapBody - SOAP envelope
 * @returns {Promise<{statusCode: number, body: string}>}
 */
async function sendGatewayRequest(host, soapBody) {
  const gatewayAddress = process.env.GATEWAY_ADDRESS || 'rdp.2c2a.com';
  const gatewayPort = parseInt(process.env.GATEWAY_PORT || '443', 10);
  const gatewayEnabled = process.env.GATEWAY_ENABLED === 'true';

  if (!gatewayEnabled) {
    throw new Error('Gateway is not enabled');
  }

  const options = {
    hostname: gatewayAddress,
    port: gatewayPort,
    useSsl: true,
    path: `/api/tunnel/${host.tunnel_token}/winrm`,
    timeout: DEFAULT_TIMEOUT,
    body: JSON.stringify({
      tunnel_token: host.tunnel_token,
      soap_body: soapBody,
      auth_method: host.authMethod || 'ntlm',
      username: host.username,
      password: host.password,
    }),
  };

  const transport = https;
  return new Promise((resolve, reject) => {
    const reqOpts = {
      hostname: options.hostname,
      port: options.port,
      path: options.path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(options.body),
      },
      timeout: options.timeout,
      rejectUnauthorized: false,
    };

    const req = transport.request(reqOpts, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const body = Buffer.concat(chunks).toString('utf8');
        try {
          const parsed = JSON.parse(body);
          resolve({
            statusCode: parsed.status_code || res.statusCode,
            body: parsed.soap_response || body,
          });
        } catch (_) {
          resolve({
            statusCode: res.statusCode,
            body,
          });
        }
      });
    });

    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('Gateway request timed out'));
    });

    req.write(options.body);
    req.end();
  });
}

/**
 * Determine which transport to use based on host config
 * @param {object} host - Host info
 * @returns {Function} Request function
 */
function getRequestFunction(host) {
  if (host.tunnel_token && host.tunnel_status === 'connected') {
    return sendGatewayRequest;
  }
  return sendWinrmRequest;
}

/**
 * Execute a command on a remote Windows host via WinRM
 * @param {object} host - Host connection info
 * @param {string} command - Command to execute
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function executeCommand(host, command) {
  const requestFn = getRequestFunction(host);

  // Step 1: Create shell
  const createEnvelope = buildCreateShellEnvelope();
  const createRes = await requestFn(host, createEnvelope);

  if (createRes.statusCode !== 200) {
    throw new Error(`Failed to create WinRM shell: HTTP ${createRes.statusCode}`);
  }

  const shellId = parseShellId(createRes.body);
  if (!shellId) {
    throw new Error('Failed to parse ShellId from WinRM response');
  }

  try {
    // Step 2: Execute command
    const execEnvelope = buildExecuteCommandEnvelope(shellId, command);
    const execRes = await requestFn(host, execEnvelope);

    if (execRes.statusCode !== 200) {
      throw new Error(`Failed to execute command: HTTP ${execRes.statusCode}`);
    }

    const commandId = parseCommandId(execRes.body);
    if (!commandId) {
      throw new Error('Failed to parse CommandId from WinRM response');
    }

    // Step 3: Receive output (loop until done)
    let stdout = '';
    let stderr = '';
    let exitCode = -1;
    let attempts = 0;
    const maxAttempts = 50;

    while (attempts < maxAttempts) {
      const recvEnvelope = buildReceiveOutputEnvelope(shellId, commandId);
      const recvRes = await requestFn(host, recvEnvelope);

      if (recvRes.statusCode !== 200) {
        throw new Error(`Failed to receive output: HTTP ${recvRes.statusCode}`);
      }

      const output = parseOutput(recvRes.body);
      stdout += output.stdout;
      stderr += output.stderr;

      if (output.done) {
        exitCode = output.exitCode;
        break;
      }

      attempts++;
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    return { stdout, stderr, exitCode };
  } finally {
    // Step 4: Delete shell
    try {
      const deleteEnvelope = buildDeleteShellEnvelope(shellId);
      await requestFn(host, deleteEnvelope);
    } catch (err) {
      console.error('[WinRM] Failed to delete shell:', err.message);
    }
  }
}

/**
 * Execute a PowerShell script on a remote Windows host via WinRM
 * @param {object} host - Host connection info
 * @param {string} script - PowerShell script
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function executePowershell(host, script) {
  const encodedScript = Buffer.from(script, 'utf16le').toString('base64');
  const command = `powershell -NoProfile -NonInteractive -EncodedCommand ${encodedScript}`;
  return executeCommand(host, command);
}

/**
 * Create a local user on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username to create
 * @param {string} password - Password for the new user
 * @param {string} description - User description
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function createUser(host, username, password, description) {
  const escapedUser = escapePowerShell(username);
  const escapedPass = escapePowerShell(password);
  const escapedDesc = escapePowerShell(description || '');

  const script = `
$ErrorActionPreference = 'Stop'
$username = '${escapedUser}'
$password = '${escapedPass}'
$description = '${escapedDesc}'

$securePassword = ConvertTo-SecureString $password -AsPlainText -Force
New-LocalUser -Name $username -Password $securePassword -Description $description -AccountNeverExpires
Write-Output "User $username created successfully"
`;

  return executePowershell(host, script);
}

/**
 * Delete a local user on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username to delete
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function deleteUser(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Remove-LocalUser -Name '${escapedUser}'
Write-Output "User ${escapedUser} deleted successfully"
`;
  return executePowershell(host, script);
}

/**
 * Enable a local user on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username to enable
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function enableUser(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Enable-LocalUser -Name '${escapedUser}'
Write-Output "User ${escapedUser} enabled successfully"
`;
  return executePowershell(host, script);
}

/**
 * Disable a local user on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username to disable
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function disableUser(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Disable-LocalUser -Name '${escapedUser}'
Write-Output "User ${escapedUser} disabled successfully"
`;
  return executePowershell(host, script);
}

/**
 * Reset password for a local user on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username
 * @param {string} newPassword - New password
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function resetPassword(host, username, newPassword) {
  const escapedUser = escapePowerShell(username);
  const escapedPass = escapePowerShell(newPassword);
  const script = `
$ErrorActionPreference = 'Stop'
$securePassword = ConvertTo-SecureString '${escapedPass}' -AsPlainText -Force
Set-LocalUser -Name '${escapedUser}' -Password $securePassword
Write-Output "Password for ${escapedUser} reset successfully"
`;
  return executePowershell(host, script);
}

/**
 * Add user to Administrators group (op user)
 * @param {object} host - Host connection info
 * @param {string} username - Username
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function opUser(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Add-LocalGroupMember -Group 'Administrators' -Member '${escapedUser}'
Write-Output "User ${escapedUser} added to Administrators group"
`;
  return executePowershell(host, script);
}

/**
 * Remove user from Administrators group (deop user)
 * @param {object} host - Host connection info
 * @param {string} username - Username
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function deopUser(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Remove-LocalGroupMember -Group 'Administrators' -Member '${escapedUser}'
Write-Output "User ${escapedUser} removed from Administrators group"
`;
  return executePowershell(host, script);
}

/**
 * Add user to Remote Desktop Users group
 * @param {object} host - Host connection info
 * @param {string} username - Username
 * @returns {Promise<{stdout: string, stderr: string, exitCode: number}>}
 */
async function addToRemoteUsers(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
Add-LocalGroupMember -Group 'Remote Desktop Users' -Member '${escapedUser}'
Write-Output "User ${escapedUser} added to Remote Desktop Users group"
`;
  return executePowershell(host, script);
}

/**
 * Check if a user exists on the remote host
 * @param {object} host - Host connection info
 * @param {string} username - Username to check
 * @returns {Promise<boolean>}
 */
async function checkUserExists(host, username) {
  const escapedUser = escapePowerShell(username);
  const script = `
$ErrorActionPreference = 'Stop'
$user = Get-LocalUser -Name '${escapedUser}' -ErrorAction SilentlyContinue
if ($user) { Write-Output 'EXISTS' } else { Write-Output 'NOT_FOUND' }
`;
  const result = await executePowershell(host, script);
  return result.stdout.trim() === 'EXISTS';
}

module.exports = {
  escapePowerShell,
  executeCommand,
  executePowershell,
  createUser,
  deleteUser,
  enableUser,
  disableUser,
  resetPassword,
  opUser,
  deopUser,
  addToRemoteUsers,
  checkUserExists,
};
