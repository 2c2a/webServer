'use strict';

const redis = require('./redis');
const db = require('./db');
const { QUEUE_NAMES } = redis;

// Queue priority order (higher priority first)
const QUEUE_PRIORITY = [
  QUEUE_NAMES.HOSTS,
  QUEUE_NAMES.OPERATIONS,
  QUEUE_NAMES.BOOTSTRAP,
  QUEUE_NAMES.CERTIFICATES,
  QUEUE_NAMES.DEFAULT,
];

// Task type to handler mapping (populated during initialization)
const taskHandlers = {};

/**
 * Register a task handler
 * @param {string} taskType - Task type identifier
 * @param {Function} handler - Async handler function(task) => result
 */
function registerHandler(taskType, handler) {
  taskHandlers[taskType] = handler;
  console.log(`[Queue] Registered handler for task type: ${taskType}`);
}

/**
 * Register multiple handlers at once
 * @param {object} handlers - Map of taskType => handler
 */
function registerHandlers(handlers) {
  for (const [type, handler] of Object.entries(handlers)) {
    registerHandler(type, handler);
  }
}

class Worker {
  constructor(options = {}) {
    this.workerId = options.workerId || `worker-${process.pid}-${Date.now()}`;
    this.queues = options.queues || QUEUE_PRIORITY;
    this.running = false;
    this.currentTask = null;
    this.heartbeatInterval = null;
    this.pollInterval = options.pollInterval || 1000;
    this.tasksProcessed = 0;
    this.tasksFailed = 0;
  }

  /**
   * Start the worker
   */
  async start() {
    console.log(`[Worker:${this.workerId}] Starting...`);
    console.log(`[Worker:${this.workerId}] Watching queues: ${this.queues.join(', ')}`);

    this.running = true;

    // Start heartbeat
    this.heartbeatInterval = setInterval(async () => {
      try {
        await redis.setWorkerHeartbeat(this.workerId, {
          status: this.currentTask ? 'busy' : 'idle',
          currentTask: this.currentTask ? this.currentTask.id : null,
          queue: this.currentTask ? this.currentTask._queue : null,
        });
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Heartbeat error:`, err.message);
      }
    }, 30000);

    // Start polling loop
    this._pollLoop();
  }

  /**
   * Main polling loop
   */
  async _pollLoop() {
    while (this.running) {
      try {
        const task = await this._pollNextTask();
        if (task) {
          await this._processTask(task);
        } else {
          // No task found, wait before polling again
          await new Promise((resolve) => setTimeout(resolve, this.pollInterval));
        }
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Poll loop error:`, err.message);
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
    }

    console.log(`[Worker:${this.workerId}] Poll loop ended`);
  }

  /**
   * Poll all queues in priority order, return first task found
   * @returns {object|null} Task object or null
   */
  async _pollNextTask() {
    for (const queue of this.queues) {
      try {
        const task = await redis.popTask(queue, 1);
        if (task) {
          task._queue = queue;
          return task;
        }
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Error polling queue ${queue}:`, err.message);
      }
    }
    return null;
  }

  /**
   * Process a single task
   * @param {object} task - Task object
   */
  async _processTask(task) {
    this.currentTask = task;
    console.log(`[Worker:${this.workerId}] Processing task ${task.id} (type: ${task.type})`);

    // Update async_tasks table: started
    try {
      await db.update(
        'async_tasks',
        { status: 'running', started_at: new Date().toISOString() },
        'task_id = $1',
        [task.id]
      );
    } catch (err) {
      console.error(`[Worker:${this.workerId}] Failed to update task status to running:`, err.message);
    }

    try {
      const handler = taskHandlers[task.type];
      if (!handler) {
        throw new Error(`No handler registered for task type: ${task.type}`);
      }

      const result = await handler(task);

      // Success
      await this._handleSuccess(task, result);
    } catch (err) {
      // Failure
      await this._handleFailure(task, err);
    } finally {
      this.currentTask = null;
      this.tasksProcessed++;
    }
  }

  /**
   * Handle successful task execution
   * @param {object} task - Task object
   * @param {*} result - Task result
   */
  async _handleSuccess(task, result) {
    console.log(`[Worker:${this.workerId}] Task ${task.id} completed successfully`);

    const now = new Date().toISOString();

    // Write result to Redis
    try {
      await redis.setTaskResult(task.id, {
        success: true,
        result: result,
        completedAt: now,
      });
    } catch (err) {
      console.error(`[Worker:${this.workerId}] Failed to write result to Redis:`, err.message);
    }

    // Update async_tasks table
    try {
      await db.update(
        'async_tasks',
        {
          status: 'completed',
          completed_at: now,
          progress: 100,
          result: JSON.stringify(result),
        },
        'task_id = $1',
        [task.id]
      );
    } catch (err) {
      console.error(`[Worker:${this.workerId}] Failed to update task status to completed:`, err.message);
    }
  }

  /**
   * Handle failed task execution
   * @param {object} task - Task object
   * @param {Error} error - Error object
   */
  async _handleFailure(task, error) {
    console.error(`[Worker:${this.workerId}] Task ${task.id} failed:`, error.message);

    const retryCount = (task.retryCount || 0) + 1;
    const maxRetries = task.maxRetries || 3;

    if (retryCount < maxRetries) {
      // Retry: push back to queue with incremented retryCount
      console.log(`[Worker:${this.workerId}] Retrying task ${task.id} (${retryCount}/${maxRetries})`);

      try {
        await redis.pushTask(task._queue, {
          ...task,
          retryCount,
        });
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Failed to requeue task:`, err.message);
      }

      // Update async_tasks table
      try {
        await db.update(
          'async_tasks',
          {
            status: 'retrying',
            error_message: `Attempt ${retryCount}/${maxRetries}: ${error.message}`,
          },
          'task_id = $1',
          [task.id]
        );
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Failed to update task status to retrying:`, err.message);
      }
    } else {
      // Max retries exceeded, mark as failed
      console.error(`[Worker:${this.workerId}] Task ${task.id} failed permanently after ${maxRetries} retries`);

      const now = new Date().toISOString();

      // Write failure result to Redis
      try {
        await redis.setTaskResult(task.id, {
          success: false,
          error: error.message,
          completedAt: now,
        });
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Failed to write failure result to Redis:`, err.message);
      }

      // Update async_tasks table
      try {
        await db.update(
          'async_tasks',
          {
            status: 'failed',
            completed_at: now,
            error_message: error.message,
          },
          'task_id = $1',
          [task.id]
        );
      } catch (err) {
        console.error(`[Worker:${this.workerId}] Failed to update task status to failed:`, err.message);
      }

      this.tasksFailed++;
    }
  }

  /**
   * Gracefully stop the worker
   */
  async stop() {
    console.log(`[Worker:${this.workerId}] Stopping...`);
    this.running = false;

    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    // Wait for current task to finish (with timeout)
    const timeout = 30000;
    const start = Date.now();
    while (this.currentTask && Date.now() - start < timeout) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }

    if (this.currentTask) {
      console.warn(`[Worker:${this.workerId}] Force stopping while task ${this.currentTask.id} is still running`);
    }

    console.log(`[Worker:${this.workerId}] Stopped. Processed: ${this.tasksProcessed}, Failed: ${this.tasksFailed}`);
  }

  /**
   * Get worker stats
   * @returns {object}
   */
  getStats() {
    return {
      workerId: this.workerId,
      running: this.running,
      currentTask: this.currentTask ? this.currentTask.id : null,
      tasksProcessed: this.tasksProcessed,
      tasksFailed: this.tasksFailed,
      queues: this.queues,
    };
  }
}

module.exports = {
  Worker,
  registerHandler,
  registerHandlers,
  QUEUE_PRIORITY,
  QUEUE_NAMES,
};
