'use strict';

const Redis = require('ioredis');

const QUEUE_NAMES = {
  HOSTS: 'queue:hosts',
  OPERATIONS: 'queue:operations',
  BOOTSTRAP: 'queue:bootstrap',
  CERTIFICATES: 'queue:certificates',
  DEFAULT: 'queue:default',
};

const RESULT_TTL = 86400; // 24 hours in seconds
const PROGRESS_CHANNEL = 'task:progress';

let client = null;
let subscriber = null;

function createClient(role = 'client') {
  const redisUrl = process.env.REDIS_URL || 'redis://127.0.0.1:6379/0';
  const c = new Redis(redisUrl, {
    maxRetriesPerRequest: 3,
    retryStrategy(times) {
      const delay = Math.min(times * 200, 5000);
      return delay;
    },
    reconnectOnError(err) {
      const targetErrors = ['READONLY', 'ECONNRESET', 'ETIMEDOUT'];
      if (targetErrors.some(e => err.message.includes(e))) {
        return true;
      }
      return false;
    },
    enableReadyCheck: true,
    lazyConnect: true,
  });

  c.on('error', (err) => {
    console.error(`[Redis:${role}] Error:`, err.message);
  });

  c.on('connect', () => {
    console.log(`[Redis:${role}] Connected`);
  });

  c.on('reconnecting', () => {
    console.log(`[Redis:${role}] Reconnecting...`);
  });

  c.on('ready', () => {
    console.log(`[Redis:${role}] Ready`);
  });

  return c;
}

function getClient() {
  if (!client) {
    client = createClient('client');
  }
  return client;
}

function getSubscriber() {
  if (!subscriber) {
    subscriber = createClient('subscriber');
  }
  return subscriber;
}

async function connect() {
  const c = getClient();
  await c.connect();
  return c;
}

async function disconnect() {
  const promises = [];
  if (client) {
    promises.push(client.quit().catch(() => {}));
    client = null;
  }
  if (subscriber) {
    promises.push(subscriber.quit().catch(() => {}));
    subscriber = null;
  }
  await Promise.all(promises);
}

/**
 * Push a task to a queue (LPUSH)
 * @param {string} queue - Queue name
 * @param {object} task - Task object {id, type, payload, retryCount, maxRetries, createdAt}
 */
async function pushTask(queue, task) {
  const c = getClient();
  const taskData = {
    id: task.id,
    type: task.type,
    payload: task.payload || {},
    retryCount: task.retryCount || 0,
    maxRetries: task.maxRetries || 3,
    createdAt: task.createdAt || new Date().toISOString(),
  };
  await c.lpush(queue, JSON.stringify(taskData));
  return taskData;
}

/**
 * Pop a task from a queue (BRPOP)
 * @param {string} queue - Queue name
 * @param {number} timeout - Timeout in seconds (0 = infinite)
 * @returns {object|null} Task object or null
 */
async function popTask(queue, timeout = 5) {
  const c = getClient();
  const result = await c.brpop(queue, timeout);
  if (!result) return null;
  try {
    return JSON.parse(result[1]);
  } catch (err) {
    console.error('[Redis] Failed to parse task JSON:', err.message);
    return null;
  }
}

/**
 * Set task result with 24h TTL
 * @param {string} taskId - Task ID
 * @param {object} result - Result object {taskId, success, result, error, completedAt}
 */
async function setTaskResult(taskId, result) {
  const c = getClient();
  const key = `task:result:${taskId}`;
  const resultData = {
    taskId,
    success: result.success !== undefined ? result.success : true,
    result: result.result || null,
    error: result.error || null,
    completedAt: result.completedAt || new Date().toISOString(),
  };
  await c.set(key, JSON.stringify(resultData), 'EX', RESULT_TTL);
  return resultData;
}

/**
 * Get task result
 * @param {string} taskId - Task ID
 * @returns {object|null} Result object or null
 */
async function getTaskResult(taskId) {
  const c = getClient();
  const key = `task:result:${taskId}`;
  const data = await c.get(key);
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch (err) {
    console.error('[Redis] Failed to parse result JSON:', err.message);
    return null;
  }
}

/**
 * Update task progress (publish to channel)
 * @param {string} taskId - Task ID
 * @param {object} progress - Progress object {percent, message}
 */
async function updateTaskProgress(taskId, progress) {
  const c = getClient();
  const progressData = {
    taskId,
    percent: progress.percent || 0,
    message: progress.message || '',
    timestamp: new Date().toISOString(),
  };
  await c.publish(PROGRESS_CHANNEL, JSON.stringify(progressData));
  return progressData;
}

/**
 * Set worker heartbeat
 * @param {string} workerId - Worker identifier
 * @param {object} status - Worker status
 */
async function setWorkerHeartbeat(workerId, status) {
  const c = getClient();
  const key = `worker:heartbeat:${workerId}`;
  const data = {
    workerId,
    status: status.status || 'idle',
    currentTask: status.currentTask || null,
    queue: status.queue || null,
    timestamp: new Date().toISOString(),
  };
  await c.set(key, JSON.stringify(data), 'EX', 60); // 60s TTL
  return data;
}

/**
 * Get queue length
 * @param {string} queue - Queue name
 * @returns {number}
 */
async function getQueueLength(queue) {
  const c = getClient();
  return c.llen(queue);
}

module.exports = {
  QUEUE_NAMES,
  RESULT_TTL,
  PROGRESS_CHANNEL,
  createClient,
  getClient,
  getSubscriber,
  connect,
  disconnect,
  pushTask,
  popTask,
  setTaskResult,
  getTaskResult,
  updateTaskProgress,
  setWorkerHeartbeat,
  getQueueLength,
};
