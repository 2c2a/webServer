'use strict';

const fs = require('fs');
const path = require('path');
const db = require('../db');
const redis = require('../redis');
const winrm = require('../winrm');
const certTasks = require('./certificateTasks');
const { getHostConnection } = require('./accountCreation');

/**
 * Cleanup expired active sessions
 * @returns {object} Result with count of deleted sessions
 */
async function cleanupExpiredSessions() {
  const result = await db.query(
    "DELETE FROM active_sessions WHERE expires_at < NOW() RETURNING session_token"
  );

  const count = result.rows.length;
  console.log(`[Bootstrap] Deleted ${count} expired sessions`);

  // Also cleanup expired user_sessions
  const userSessionsResult = await db.query(
    "DELETE FROM user_sessions WHERE expires_at < NOW() RETURNING id"
  );

  const userSessionCount = userSessionsResult.rows.length;
  console.log(`[Bootstrap] Deleted ${userSessionCount} expired user sessions`);

  return {
    activeSessionCount: count,
    userSessionCount: userSessionCount,
    message: `Cleaned up ${count} active sessions and ${userSessionCount} user sessions`,
  };
}

/**
 * Cleanup expired initial tokens (expired > 7 days)
 * @returns {object} Result with count of deleted tokens
 */
async function cleanupExpiredInitialTokens() {
  const result = await db.query(
    "DELETE FROM initial_tokens WHERE expires_at < NOW() - INTERVAL '7 days' RETURNING token"
  );

  const count = result.rows.length;
  console.log(`[Bootstrap] Deleted ${count} expired initial tokens (> 7 days old)`);

  return { count, message: `Deleted ${count} expired initial tokens` };
}

/**
 * Generate bootstrap configuration for a host
 * @param {string} hostname - Host hostname
 * @param {string} ipAddress - Host IP address
 * @param {number} operatorId - User ID performing the operation
 * @returns {object} Result with bootstrap config
 */
async function generateBootstrapConfig(hostname, ipAddress, operatorId) {
  // Find the host by hostname
  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE hostname = $1',
    [hostname]
  );

  if (!hostRow) {
    throw new Error(`Host with hostname ${hostname} not found`);
  }

  // Generate a bootstrap token
  const crypto = require('crypto');
  const token = crypto.randomBytes(32).toString('hex');
  const pairingCode = String(Math.floor(100000 + Math.random() * 900000));
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000); // 1 hour

  // Create initial token
  await db.insert('initial_tokens', {
    token: token,
    host_id: hostRow.id,
    expires_at: expiresAt.toISOString(),
    status: 'ISSUED',
    pairing_code: pairingCode,
    pairing_code_expires_at: new Date(Date.now() + 10 * 60 * 1000).toISOString(), // 10 minutes
    pairing_attempts: 0,
  });

  const config = {
    server_url: process.env.APP_URL || 'http://localhost:8080',
    token: token,
    hostname: hostname,
    ip_address: ipAddress,
    pairing_code: pairingCode,
  };

  return {
    hostId: hostRow.id,
    config,
    message: 'Bootstrap configuration generated',
  };
}

/**
 * Initialize host bootstrap process
 * @param {number} hostId - hosts.id
 * @param {number} operatorId - User ID performing the operation
 * @returns {object} Result
 */
async function initializeHostBootstrap(hostId, operatorId) {
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [hostId]);
  if (!hostRow) {
    throw new Error(`Host ${hostId} not found`);
  }

  // Create async task record
  const asyncTask = await db.insert('async_tasks', {
    task_id: `bootstrap-${hostId}-${Date.now()}`,
    name: `Initialize bootstrap for ${hostRow.name}`,
    status: 'running',
    created_by_id: operatorId,
    started_at: new Date().toISOString(),
    target_object_id: hostId,
    target_content_type: 'host',
  });

  try {
    await redis.updateTaskProgress(asyncTask.task_id, { percent: 10, message: 'Generating bootstrap configuration' });

    // Generate bootstrap config
    const configResult = await generateBootstrapConfig(
      hostRow.hostname,
      '', // IP will be detected by the bootstrap agent
      operatorId
    );

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 50, message: 'Bootstrap configuration generated' });

    // Update host status
    await db.update('hosts', {
      tunnel_status: 'pending_bootstrap',
      cert_provision_status: 'pending',
    }, 'id = $1', [hostId]);

    await redis.updateTaskProgress(asyncTask.task_id, { percent: 100, message: 'Bootstrap initialized' });

    // Update async task
    await db.update('async_tasks', {
      status: 'completed',
      completed_at: new Date().toISOString(),
      progress: 100,
      result: JSON.stringify(configResult),
    }, 'id = $1', [asyncTask.id]);

    return configResult;
  } catch (err) {
    await db.update('async_tasks', {
      status: 'failed',
      completed_at: new Date().toISOString(),
      error_message: err.message,
    }, 'id = $1', [asyncTask.id]);

    throw err;
  }
}

/**
 * Issue server and client certificates for a provision token
 * @param {string} tokenStr - cert_provision_tokens.token
 * @returns {object} Result with certificate info
 */
async function certProvisionIssueCerts(tokenStr) {
  const token = await db.fetchOne(
    'SELECT * FROM cert_provision_tokens WHERE token = $1',
    [tokenStr]
  );

  if (!token) {
    throw new Error(`Provision token ${tokenStr} not found`);
  }

  if (token.status !== 'ISSUED') {
    throw new Error(`Token ${tokenStr} is not in ISSUED state (status: ${token.status})`);
  }

  if (new Date(token.expires_at) < new Date()) {
    await db.update('cert_provision_tokens', { status: 'EXPIRED' }, 'token = $1', [tokenStr]);
    throw new Error(`Token ${tokenStr} has expired`);
  }

  // Get the host
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [token.host_id]);
  if (!hostRow) {
    throw new Error(`Host ${token.host_id} not found`);
  }

  // Get or create CA
  let ca = await db.fetchOne(
    "SELECT * FROM certificate_authorities WHERE is_active = true ORDER BY created_at DESC LIMIT 1"
  );

  if (!ca) {
    // Generate a new CA
    const caResult = certTasks.generateCA();
    ca = await db.insert('certificate_authorities', {
      name: `2c2a-CA-${Date.now()}`,
      cert_root: hostRow.cert_root || 'R',
      cert_sub: hostRow.cert_sub || 'S',
      expires_at: new Date(Date.now() + 10 * 365 * 24 * 60 * 60 * 1000).toISOString(), // 10 years
      is_active: true,
      description: 'Auto-generated CA',
    });

    // Store CA key and cert in cert_data
    ca._caKey = caResult.caKeyPem;
    ca._caCert = caResult.caCertPem;
  } else {
    // Retrieve CA key and cert from token or host data
    // In production, these would be stored securely
    const caData = token.cert_data || {};
    ca._caKey = caData.caKey;
    ca._caCert = caData.caCert;
  }

  if (!ca._caKey || !ca._caCert) {
    throw new Error('CA key/cert not available for certificate issuance');
  }

  // Issue server certificate
  const serverCert = certTasks.issueServerCert(
    ca._caKey,
    ca._caCert,
    token.hostname || hostRow.hostname,
    token.ip_address || ''
  );

  // Issue client certificate for UPN
  const upnValue = `${hostRow.hostname}$${hostRow.cert_root || 'R'}${hostRow.cert_sub || 'S'}`;
  const clientCert = certTasks.issueClientCert(
    ca._caKey,
    ca._caCert,
    upnValue
  );

  // Store server certificate
  await db.insert('server_certificates', {
    hostname: token.hostname || hostRow.hostname,
    ip_address: token.ip_address || null,
    ca_id: ca.id,
    thumbprint: serverCert.thumbprint,
    expires_at: serverCert.expiresAt,
    is_revoked: false,
  });

  // Store client certificate
  await db.insert('client_certificates', {
    name: `${hostRow.hostname}-client`,
    upn_value: upnValue,
    ca_id: ca.id,
    thumbprint: clientCert.thumbprint,
    expires_at: clientCert.expiresAt,
    is_active: true,
    description: `Client cert for host ${hostRow.name}`,
  });

  // Update token status
  await db.update('cert_provision_tokens', {
    status: 'CONSUMED',
    consumed_at: new Date().toISOString(),
    cert_data: JSON.stringify({
      serverCert: serverCert.certPem,
      serverKey: serverCert.keyPem,
      clientCert: clientCert.certPem,
      clientKey: clientCert.keyPem,
      pfxPassword: hostRow.pfx_password || '',
    }),
  }, 'token = $1', [tokenStr]);

  // Update host
  await db.update('hosts', {
    cert_provision_status: 'completed',
    cert_activated_at: new Date().toISOString(),
  }, 'id = $1', [hostRow.id]);

  return {
    hostId: hostRow.id,
    serverCertThumbprint: serverCert.thumbprint,
    clientCertThumbprint: clientCert.thumbprint,
    message: 'Certificates issued successfully',
  };
}

/**
 * Cleanup expired provision tokens
 * @returns {object} Result with count
 */
async function cleanupExpiredProvisionTokens() {
  const result = await db.query(
    "UPDATE cert_provision_tokens SET status = 'EXPIRED' WHERE status = 'ISSUED' AND expires_at < NOW() RETURNING token"
  );

  const count = result.rows.length;
  console.log(`[Bootstrap] Expired ${count} provision tokens`);

  return { count, message: `Expired ${count} provision tokens` };
}

/**
 * Cleanup unactivated certificates (certificates not activated within 24h of creation)
 * @returns {object} Result with count
 */
async function cleanupUnactivatedCertificates() {
  const result = await db.query(
    `UPDATE hosts SET cert_provision_status = 'expired'
     WHERE cert_provision_status = 'pending'
     AND cert_activated_at IS NULL
     AND created_at < NOW() - INTERVAL '24 hours'
     RETURNING id`
  );

  const count = result.rows.length;
  console.log(`[Bootstrap] Marked ${count} unactivated certificates as expired`);

  return { count, message: `Marked ${count} unactivated certificates as expired` };
}

/**
 * Cleanup orphan certificate directories
 * @returns {object} Result with count
 */
async function cleanupOrphanCertDirs() {
  const certDir = process.env.CERT_DIR || '/var/lib/2c2a/certs';
  let count = 0;

  try {
    if (!fs.existsSync(certDir)) {
      return { count: 0, message: 'Certificate directory does not exist' };
    }

    const entries = fs.readdirSync(certDir, { withFileTypes: true });

    for (const entry of entries) {
      if (!entry.isDirectory()) continue;

      const dirPath = path.join(certDir, entry.name);

      // Check if this directory corresponds to a host
      const host = await db.fetchOne(
        "SELECT id FROM hosts WHERE hostname = $1 OR CAST(id AS TEXT) = $1",
        [entry.name]
      );

      if (!host) {
        // Orphan directory - remove it
        try {
          fs.rmSync(dirPath, { recursive: true, force: true });
          count++;
          console.log(`[Bootstrap] Removed orphan cert directory: ${dirPath}`);
        } catch (err) {
          console.error(`[Bootstrap] Failed to remove orphan cert dir ${dirPath}:`, err.message);
        }
      }
    }
  } catch (err) {
    console.error('[Bootstrap] Error cleaning up orphan cert dirs:', err.message);
  }

  return { count, message: `Removed ${count} orphan certificate directories` };
}

// Task handler mapping
const handlers = {
  cleanup_expired_sessions: cleanupExpiredSessions,
  cleanup_expired_initial_tokens: cleanupExpiredInitialTokens,
  generate_bootstrap_config: (task) => generateBootstrapConfig(
    task.payload.hostname,
    task.payload.ipAddress,
    task.payload.operatorId
  ),
  initialize_host_bootstrap: (task) => initializeHostBootstrap(
    task.payload.hostId,
    task.payload.operatorId
  ),
  cert_provision_issue_certs: (task) => certProvisionIssueCerts(task.payload.token),
  cleanup_expired_provision_tokens: cleanupExpiredProvisionTokens,
  cleanup_unactivated_certificates: cleanupUnactivatedCertificates,
  cleanup_orphan_cert_dirs: cleanupOrphanCertDirs,
};

module.exports = {
  cleanupExpiredSessions,
  cleanupExpiredInitialTokens,
  generateBootstrapConfig,
  initializeHostBootstrap,
  certProvisionIssueCerts,
  cleanupExpiredProvisionTokens,
  cleanupUnactivatedCertificates,
  cleanupOrphanCertDirs,
  handlers,
};
