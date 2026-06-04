'use strict';

const crypto = require('crypto');
const db = require('../db');
const redis = require('../redis');
const winrm = require('../winrm');

/**
 * Generate a complex random password
 * @param {number} length - Password length (default 16)
 * @returns {string}
 */
function generatePassword(length = 16) {
  const lowercase = 'abcdefghijkmnopqrstuvwxyz';
  const uppercase = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const numbers = '23456789';
  const special = '!@#$%^&*_-+=';
  const all = lowercase + uppercase + numbers + special;

  let password = '';
  // Ensure at least one of each type
  password += lowercase[crypto.randomInt(lowercase.length)];
  password += uppercase[crypto.randomInt(uppercase.length)];
  password += numbers[crypto.randomInt(numbers.length)];
  password += special[crypto.randomInt(special.length)];

  for (let i = password.length; i < length; i++) {
    password += all[crypto.randomInt(all.length)];
  }

  // Shuffle
  return password.split('').sort(() => crypto.randomInt(2) - 1).join('');
}

/**
 * Get host connection info from DB host record
 * @param {object} hostRow - hosts table row
 * @returns {object} WinRM connection info
 */
function getHostConnection(hostRow) {
  return {
    hostname: hostRow.hostname,
    port: hostRow.port || 5985,
    useSsl: hostRow.use_ssl || false,
    authMethod: hostRow.auth_method || 'ntlm',
    username: hostRow.username,
    password: hostRow.password,
    certPemPath: hostRow.cert_pem_path,
    certKeyPath: hostRow.cert_key_path,
    tunnel_token: hostRow.tunnel_token,
    tunnel_status: hostRow.tunnel_status,
  };
}

/**
 * Process an approved account opening request
 * @param {object} task - Task object with payload.requestId
 * @returns {object} Result
 */
async function processAccountCreation(task) {
  const requestId = task.payload.requestId;
  if (!requestId) {
    throw new Error('Missing requestId in payload');
  }

  console.log(`[AccountCreation] Processing request ${requestId}`);

  // 1. Get request from DB
  const request = await db.fetchOne(
    'SELECT * FROM account_opening_requests WHERE id = $1',
    [requestId]
  );

  if (!request) {
    throw new Error(`Account opening request ${requestId} not found`);
  }

  if (request.status !== 'approved') {
    throw new Error(`Request ${requestId} is not approved (status: ${request.status})`);
  }

  // 2. Get product and host info
  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [request.target_product_id]
  );

  if (!product) {
    throw new Error(`Product ${request.target_product_id} not found`);
  }

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  if (!hostRow) {
    throw new Error(`Host ${product.host_id} not found`);
  }

  const hostConn = getHostConnection(hostRow);

  // 3. Generate complex password
  const password = generatePassword();

  // 4. Connect to host via WinRM and create user
  await redis.updateTaskProgress(task.id, { percent: 20, message: 'Creating user on remote host' });

  const username = request.username;
  const description = request.user_description || `Cloud user: ${request.user_fullname}`;

  try {
    const createResult = await winrm.createUser(hostConn, username, password, description);

    if (createResult.exitCode !== 0) {
      throw new Error(`Failed to create user on remote host: ${createResult.stderr}`);
    }
  } catch (err) {
    // Update request status to failed
    await db.update(
      'account_opening_requests',
      {
        status: 'failed',
        result_message: `Remote user creation failed: ${err.message}`,
      },
      'id = $1',
      [requestId]
    );
    throw err;
  }

  // 5. Add to Remote Desktop Users group
  await redis.updateTaskProgress(task.id, { percent: 40, message: 'Adding to Remote Desktop Users' });

  try {
    await winrm.addToRemoteUsers(hostConn, username);
  } catch (err) {
    console.error(`[AccountCreation] Failed to add ${username} to Remote Desktop Users:`, err.message);
    // Non-fatal, continue
  }

  // 6. Set disk quota if configured
  if (product.enable_disk_quota) {
    await redis.updateTaskProgress(task.id, { percent: 50, message: 'Setting disk quota' });

    const diskQuota = request.requested_disk_capacity || product.default_disk_quota || {};
    if (Object.keys(diskQuota).length > 0) {
      try {
        await remoteSetUserDiskQuotas(null, diskQuota, hostConn, username);
      } catch (err) {
        console.error(`[AccountCreation] Failed to set disk quota:`, err.message);
        // Non-fatal, continue
      }
    }
  }

  // 7. Create CloudComputerUser record in DB
  await redis.updateTaskProgress(task.id, { percent: 70, message: 'Creating database record' });

  const cloudUser = await db.insert('cloud_computer_users', {
    username: username,
    fullname: request.user_fullname,
    email: request.user_email,
    description: description,
    product_id: product.id,
    status: 'active',
    is_admin: false,
    disk_quota: request.requested_disk_capacity || product.default_disk_quota || {},
    created_from_request_id: requestId,
    owner_id: request.applicant_id,
    initial_password: password,
    password_viewed: false,
  });

  // 8. Update request status to completed
  await redis.updateTaskProgress(task.id, { percent: 90, message: 'Completing request' });

  await db.update(
    'account_opening_requests',
    {
      status: 'completed',
      cloud_user_id: String(cloudUser.id),
      cloud_user_password: password,
      result_message: 'Account created successfully',
    },
    'id = $1',
    [requestId]
  );

  // 9. Allocate RDP domain if applicable
  try {
    await allocateRdpDomain(request.applicant_id, product.id);
  } catch (err) {
    console.error(`[AccountCreation] Failed to allocate RDP domain:`, err.message);
    // Non-fatal
  }

  await redis.updateTaskProgress(task.id, { percent: 100, message: 'Account creation complete' });

  console.log(`[AccountCreation] Successfully created account for ${username} (request ${requestId})`);

  return {
    requestId,
    username,
    cloudUserId: cloudUser.id,
    message: 'Account created successfully',
  };
}

/**
 * Execute a remote action on a cloud user (disable/enable/delete)
 * @param {number} userId - cloud_computer_users.id
 * @param {string} action - 'disable', 'enable', or 'delete'
 * @returns {object} Result
 */
async function executeCloudUserRemoteAction(userId, action) {
  const cloudUser = await db.fetchOne(
    'SELECT * FROM cloud_computer_users WHERE id = $1',
    [userId]
  );

  if (!cloudUser) {
    throw new Error(`Cloud computer user ${userId} not found`);
  }

  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [cloudUser.product_id]
  );

  if (!product) {
    throw new Error(`Product ${cloudUser.product_id} not found`);
  }

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  if (!hostRow) {
    throw new Error(`Host ${product.host_id} not found`);
  }

  const hostConn = getHostConnection(hostRow);
  const username = cloudUser.username;

  let result;
  switch (action) {
    case 'disable':
      result = await winrm.disableUser(hostConn, username);
      await db.update('cloud_computer_users', { status: 'disabled' }, 'id = $1', [userId]);
      break;
    case 'enable':
      result = await winrm.enableUser(hostConn, username);
      await db.update('cloud_computer_users', { status: 'active' }, 'id = $1', [userId]);
      break;
    case 'delete':
      result = await winrm.deleteUser(hostConn, username);
      await db.update('cloud_computer_users', { status: 'deleted' }, 'id = $1', [userId]);
      break;
    default:
      throw new Error(`Unknown action: ${action}`);
  }

  if (result.exitCode !== 0) {
    throw new Error(`Remote action ${action} failed: ${result.stderr}`);
  }

  return { userId, action, message: `User ${username} ${action}d successfully` };
}

/**
 * Add cloud user to Administrators group
 * @param {number} cloudUserId - cloud_computer_users.id
 * @returns {object} Result
 */
async function remoteSetAdmin(cloudUserId) {
  const cloudUser = await db.fetchOne(
    'SELECT * FROM cloud_computer_users WHERE id = $1',
    [cloudUserId]
  );

  if (!cloudUser) {
    throw new Error(`Cloud computer user ${cloudUserId} not found`);
  }

  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [cloudUser.product_id]
  );

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  const hostConn = getHostConnection(hostRow);
  const result = await winrm.opUser(hostConn, cloudUser.username);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to set admin: ${result.stderr}`);
  }

  await db.update('cloud_computer_users', { is_admin: true }, 'id = $1', [cloudUserId]);

  return { cloudUserId, message: `User ${cloudUser.username} promoted to admin` };
}

/**
 * Remove cloud user from Administrators group
 * @param {number} cloudUserId - cloud_computer_users.id
 * @returns {object} Result
 */
async function remoteRemoveAdmin(cloudUserId) {
  const cloudUser = await db.fetchOne(
    'SELECT * FROM cloud_computer_users WHERE id = $1',
    [cloudUserId]
  );

  if (!cloudUser) {
    throw new Error(`Cloud computer user ${cloudUserId} not found`);
  }

  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [cloudUser.product_id]
  );

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  const hostConn = getHostConnection(hostRow);
  const result = await winrm.deopUser(hostConn, cloudUser.username);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to remove admin: ${result.stderr}`);
  }

  await db.update('cloud_computer_users', { is_admin: false }, 'id = $1', [cloudUserId]);

  return { cloudUserId, message: `User ${cloudUser.username} removed from admin` };
}

/**
 * Reset password for a cloud user
 * @param {number} cloudUserId - cloud_computer_users.id
 * @param {string} newPassword - New password (optional, auto-generated if not provided)
 * @returns {object} Result with new password
 */
async function remoteResetPassword(cloudUserId, newPassword) {
  const cloudUser = await db.fetchOne(
    'SELECT * FROM cloud_computer_users WHERE id = $1',
    [cloudUserId]
  );

  if (!cloudUser) {
    throw new Error(`Cloud computer user ${cloudUserId} not found`);
  }

  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [cloudUser.product_id]
  );

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  const password = newPassword || generatePassword();
  const hostConn = getHostConnection(hostRow);
  const result = await winrm.resetPassword(hostConn, cloudUser.username, password);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to reset password: ${result.stderr}`);
  }

  await db.update('cloud_computer_users', {
    initial_password: password,
    password_viewed: false,
  }, 'id = $1', [cloudUserId]);

  return { cloudUserId, newPassword: password, message: `Password reset for ${cloudUser.username}` };
}

/**
 * Set disk quota for a single disk
 * @param {number} cloudUserId - cloud_computer_users.id
 * @param {string} disk - Disk identifier (e.g., 'C')
 * @param {number} quotaMb - Quota in MB
 * @returns {object} Result
 */
async function remoteSetDiskQuota(cloudUserId, disk, quotaMb) {
  const cloudUser = await db.fetchOne(
    'SELECT * FROM cloud_computer_users WHERE id = $1',
    [cloudUserId]
  );

  if (!cloudUser) {
    throw new Error(`Cloud computer user ${cloudUserId} not found`);
  }

  const product = await db.fetchOne(
    'SELECT * FROM products WHERE id = $1',
    [cloudUser.product_id]
  );

  const hostRow = await db.fetchOne(
    'SELECT * FROM hosts WHERE id = $1',
    [product.host_id]
  );

  const hostConn = getHostConnection(hostRow);
  const escapedUser = winrm.escapePowerShell(cloudUser.username);
  const escapedDisk = winrm.escapePowerShell(disk);

  const script = `
$ErrorActionPreference = 'Stop'
$username = '${escapedUser}'
$disk = '${escapedDisk}'
$quotaMB = ${quotaMb}

$quota = New-Object System.Security.AccessControl.FileSystemSecurity
$path = "${escapedDisk}:\\"

# Use fsutil to set quota
fsutil quota modify ${escapedDisk}: ${(quotaMb * 1024 * 1024)} ${(quotaMb * 1024 * 1024)} $username
Write-Output "Disk quota set for $username on ${escapedDisk}: ${quotaMb}MB"
`;

  const result = await winrm.executePowershell(hostConn, script);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to set disk quota: ${result.stderr}`);
  }

  // Update disk_quota in DB
  const currentQuota = cloudUser.disk_quota || {};
  currentQuota[disk] = quotaMb;
  await db.update('cloud_computer_users', { disk_quota: JSON.stringify(currentQuota) }, 'id = $1', [cloudUserId]);

  return { cloudUserId, disk, quotaMb, message: `Disk quota set for ${cloudUser.username} on ${disk}: ${quotaMb}MB` };
}

/**
 * Set multiple disk quotas for a user
 * @param {number} cloudUserId - cloud_computer_users.id
 * @param {object} diskQuota - Map of disk => quotaMB
 * @param {object} [hostConn] - Optional pre-resolved host connection
 * @param {string} [username] - Optional pre-resolved username
 * @returns {object} Result
 */
async function remoteSetUserDiskQuotas(cloudUserId, diskQuota, hostConn, username) {
  if (!hostConn || !username) {
    const cloudUser = await db.fetchOne(
      'SELECT * FROM cloud_computer_users WHERE id = $1',
      [cloudUserId]
    );

    if (!cloudUser) {
      throw new Error(`Cloud computer user ${cloudUserId} not found`);
    }

    username = cloudUser.username;

    const product = await db.fetchOne(
      'SELECT * FROM products WHERE id = $1',
      [cloudUser.product_id]
    );

    const hostRow = await db.fetchOne(
      'SELECT * FROM hosts WHERE id = $1',
      [product.host_id]
    );

    hostConn = getHostConnection(hostRow);
  }

  const escapedUser = winrm.escapePowerShell(username);

  // Build a single PowerShell script that sets all quotas
  const quotaLines = Object.entries(diskQuota).map(([disk, quotaMb]) => {
    const escapedDisk = winrm.escapePowerShell(disk);
    return `fsutil quota modify ${escapedDisk}: ${(quotaMb * 1024 * 1024)} ${(quotaMb * 1024 * 1024)} '${escapedUser}'`;
  });

  const script = `
$ErrorActionPreference = 'Stop'
$username = '${escapedUser}'
${quotaLines.join('\n')}
Write-Output "All disk quotas set for $username"
`;

  const result = await winrm.executePowershell(hostConn, script);

  if (result.exitCode !== 0) {
    throw new Error(`Failed to set disk quotas: ${result.stderr}`);
  }

  // Update disk_quota in DB if cloudUserId provided
  if (cloudUserId) {
    await db.update('cloud_computer_users', { disk_quota: JSON.stringify(diskQuota) }, 'id = $1', [cloudUserId]);
  }

  return { cloudUserId, diskQuota, message: `Disk quotas set for ${username}` };
}

/**
 * Allocate an RDP domain route for a user/product
 * @param {number} userId - users.id
 * @param {number} productId - products.id
 * @returns {object} Result
 */
async function allocateRdpDomain(userId, productId) {
  const rdpDomain = process.env.RDP_DOMAIN || '2c2a.com';
  if (!rdpDomain) {
    return { message: 'RDP domain not configured, skipping' };
  }

  // Check if user already has an active route for this product
  const existing = await db.fetchOne(
    'SELECT * FROM rdp_domain_routes WHERE assigned_to_id = $1 AND product_id = $2 AND is_active = true',
    [userId, productId]
  );

  if (existing) {
    // Extend expiration
    const newExpiry = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24 hours
    await db.update('rdp_domain_routes', { expires_at: newExpiry.toISOString() }, 'id = $1', [existing.id]);
    return { routeId: existing.id, domain: existing.domain, message: 'Existing route extended' };
  }

  // Generate a unique subdomain
  const subdomain = crypto.randomBytes(4).toString('hex');
  const domain = `${subdomain}.${rdpDomain}`;

  // Get product info for tunnel token
  const product = await db.fetchOne('SELECT * FROM products WHERE id = $1', [productId]);
  const hostRow = await db.fetchOne('SELECT * FROM hosts WHERE id = $1', [product.host_id]);

  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000); // 24 hours

  const route = await db.insert('rdp_domain_routes', {
    domain: domain,
    product_id: productId,
    assigned_to_id: userId,
    tunnel_token: hostRow.tunnel_token || '',
    is_active: true,
    expires_at: expiresAt.toISOString(),
  });

  return { routeId: route.id, domain, message: 'RDP domain route allocated' };
}

/**
 * Cleanup expired RDP domain routes
 * @returns {object} Result with count of deactivated routes
 */
async function cleanupExpiredRdpDomains() {
  const result = await db.query(
    "UPDATE rdp_domain_routes SET is_active = false WHERE is_active = true AND expires_at < NOW() RETURNING id"
  );

  const count = result.rows.length;
  console.log(`[AccountCreation] Deactivated ${count} expired RDP domain routes`);

  return { deactivatedCount: count, message: `Deactivated ${count} expired RDP domain routes` };
}

// Task handler mapping
const handlers = {
  process_account_creation: processAccountCreation,
  execute_cloud_user_remote_action: (task) => executeCloudUserRemoteAction(
    task.payload.userId,
    task.payload.action
  ),
  remote_set_admin: (task) => remoteSetAdmin(task.payload.cloudUserId),
  remote_remove_admin: (task) => remoteRemoveAdmin(task.payload.cloudUserId),
  remote_reset_password: (task) => remoteResetPassword(
    task.payload.cloudUserId,
    task.payload.newPassword
  ),
  remote_set_disk_quota: (task) => remoteSetDiskQuota(
    task.payload.cloudUserId,
    task.payload.disk,
    task.payload.quotaMb
  ),
  remote_set_user_disk_quotas: (task) => remoteSetUserDiskQuotas(
    task.payload.cloudUserId,
    task.payload.diskQuota
  ),
  allocate_rdp_domain: (task) => allocateRdpDomain(
    task.payload.userId,
    task.payload.productId
  ),
  cleanup_expired_rdp_domains: cleanupExpiredRdpDomains,
};

module.exports = {
  processAccountCreation,
  executeCloudUserRemoteAction,
  remoteSetAdmin,
  remoteRemoveAdmin,
  remoteResetPassword,
  remoteSetDiskQuota,
  remoteSetUserDiskQuotas,
  allocateRdpDomain,
  cleanupExpiredRdpDomains,
  generatePassword,
  getHostConnection,
  handlers,
};
