'use strict';

const db = require('../db');

/**
 * Disable users inactive for more than N days
 * @param {number} daysInactive - Number of days of inactivity (default: 90)
 * @returns {object} Result with count of disabled users
 */
async function cleanupInactiveUsers(daysInactive = 90) {
  // Find cloud computer users whose owners haven't logged in recently
  const result = await db.query(
    `UPDATE cloud_computer_users SET status = 'disabled'
     WHERE status = 'active'
     AND owner_id IN (
       SELECT u.id FROM users u
       WHERE u.last_login_at IS NULL OR u.last_login_at < NOW() - ($1 || ' days')::INTERVAL
     )
     RETURNING id, username`,
    [daysInactive]
  );

  const count = result.rows.length;
  console.log(`[Cleanup] Disabled ${count} inactive users (>${daysInactive} days)`);

  return { count, daysInactive, message: `Disabled ${count} inactive users (>${daysInactive} days inactive)` };
}

/**
 * Delete audit logs older than N days
 * @param {number} daysOld - Number of days (default: 365)
 * @returns {object} Result with count of deleted logs
 */
async function cleanupOldAuditLogs(daysOld = 365) {
  const result = await db.query(
    'DELETE FROM audit_logs WHERE timestamp < NOW() - ($1 || \' days\')::INTERVAL RETURNING id',
    [daysOld]
  );

  const count = result.rows.length;
  console.log(`[Cleanup] Deleted ${count} audit logs older than ${daysOld} days`);

  return { count, daysOld, message: `Deleted ${count} audit logs older than ${daysOld} days` };
}

/**
 * Delete login logs older than N days
 * @param {number} daysOld - Number of days (default: 180)
 * @returns {object} Result with count of deleted logs
 */
async function cleanupOldLoginLogs(daysOld = 180) {
  const result = await db.query(
    'DELETE FROM login_logs WHERE created_at < NOW() - ($1 || \' days\')::INTERVAL RETURNING id',
    [daysOld]
  );

  const count = result.rows.length;
  console.log(`[Cleanup] Deleted ${count} login logs older than ${daysOld} days`);

  return { count, daysOld, message: `Deleted ${count} login logs older than ${daysOld} days` };
}

// Task handler mapping
const handlers = {
  cleanup_inactive_users: (task) => cleanupInactiveUsers(task.payload.daysInactive || 90),
  cleanup_old_audit_logs: (task) => cleanupOldAuditLogs(task.payload.daysOld || 365),
  cleanup_old_login_logs: (task) => cleanupOldLoginLogs(task.payload.daysOld || 180),
};

module.exports = {
  cleanupInactiveUsers,
  cleanupOldAuditLogs,
  cleanupOldLoginLogs,
  handlers,
};
