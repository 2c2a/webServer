'use strict';

const cron = require('node-cron');
const crypto = require('crypto');
const redis = require('./redis');
const { QUEUE_NAMES } = redis;

const scheduledJobs = [];

/**
 * Generate a unique task ID
 * @param {string} prefix - Task type prefix
 * @returns {string}
 */
function generateTaskId(prefix) {
  return `${prefix}-${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
}

/**
 * Push a scheduled task to a queue
 * @param {string} queue - Target queue
 * @param {string} taskType - Task type
 * @param {object} payload - Task payload
 */
async function dispatchScheduledTask(queue, taskType, payload) {
  const taskId = generateTaskId(taskType);
  try {
    await redis.pushTask(queue, {
      id: taskId,
      type: taskType,
      payload: payload || {},
      retryCount: 0,
      maxRetries: 1,
      createdAt: new Date().toISOString(),
    });
    console.log(`[Scheduler] Dispatched task ${taskId} (type: ${taskType}) to ${queue}`);
  } catch (err) {
    console.error(`[Scheduler] Failed to dispatch task ${taskType}:`, err.message);
  }
}

/**
 * Schedule all periodic tasks
 */
function start() {
  console.log('[Scheduler] Starting scheduled tasks...');

  // Every day at 00:00: cleanup expired provision tokens
  const job1 = cron.schedule('0 0 * * *', async () => {
    console.log('[Scheduler] Running: cleanup expired provision tokens');
    await dispatchScheduledTask(
      QUEUE_NAMES.BOOTSTRAP,
      'cleanup_expired_provision_tokens',
      {}
    );
  }, { scheduled: true });
  scheduledJobs.push(job1);

  // Every day at 00:00: cleanup unactivated certificates
  const job2 = cron.schedule('0 0 * * *', async () => {
    console.log('[Scheduler] Running: cleanup unactivated certificates');
    await dispatchScheduledTask(
      QUEUE_NAMES.BOOTSTRAP,
      'cleanup_unactivated_certificates',
      {}
    );
  }, { scheduled: true });
  scheduledJobs.push(job2);

  // Every day at 00:00: cleanup orphan cert directories
  const job3 = cron.schedule('0 0 * * *', async () => {
    console.log('[Scheduler] Running: cleanup orphan cert directories');
    await dispatchScheduledTask(
      QUEUE_NAMES.BOOTSTRAP,
      'cleanup_orphan_cert_dirs',
      {}
    );
  }, { scheduled: true });
  scheduledJobs.push(job3);

  // Every 10 minutes: cleanup expired RDP domain routes
  const job4 = cron.schedule('*/10 * * * *', async () => {
    console.log('[Scheduler] Running: cleanup expired RDP domain routes');
    await dispatchScheduledTask(
      QUEUE_NAMES.OPERATIONS,
      'cleanup_expired_rdp_domains',
      {}
    );
  }, { scheduled: true });
  scheduledJobs.push(job4);

  // Every 5 minutes: cleanup expired sessions
  const job5 = cron.schedule('*/5 * * * *', async () => {
    console.log('[Scheduler] Running: cleanup expired sessions');
    await dispatchScheduledTask(
      QUEUE_NAMES.BOOTSTRAP,
      'cleanup_expired_sessions',
      {}
    );
  }, { scheduled: true });
  scheduledJobs.push(job5);

  console.log(`[Scheduler] Started ${scheduledJobs.length} scheduled jobs`);
}

/**
 * Stop all scheduled tasks
 */
function stop() {
  console.log('[Scheduler] Stopping scheduled tasks...');
  for (const job of scheduledJobs) {
    job.stop();
  }
  scheduledJobs.length = 0;
  console.log('[Scheduler] All scheduled jobs stopped');
}

/**
 * Get list of active jobs
 * @returns {Array}
 */
function getActiveJobs() {
  return scheduledJobs.map((job, i) => ({
    index: i,
    running: job.running || false,
  }));
}

module.exports = {
  start,
  stop,
  getActiveJobs,
  dispatchScheduledTask,
  generateTaskId,
};
