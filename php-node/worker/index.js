'use strict';

const fs = require('fs');
const path = require('path');

// Load environment variables from .env file (manual parsing, no dependency)
function loadEnvFile() {
  const envPaths = [
    path.resolve(__dirname, '..', '.env'),
    path.resolve(__dirname, '.env'),
  ];

  for (const envPath of envPaths) {
    if (fs.existsSync(envPath)) {
      console.log(`[Main] Loading .env from ${envPath}`);
      const content = fs.readFileSync(envPath, 'utf8');
      for (const line of content.split('\n')) {
        const trimmed = line.trim();
        // Skip comments and empty lines
        if (!trimmed || trimmed.startsWith('#')) continue;

        const match = trimmed.match(/^([^=]+)=(.*)$/);
        if (match) {
          const key = match[1].trim();
          let value = match[2].trim();
          // Remove surrounding quotes
          if ((value.startsWith('"') && value.endsWith('"')) ||
              (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
          }
          // Only set if not already defined in environment
          if (process.env[key] === undefined) {
            process.env[key] = value;
          }
        }
      }
      return;
    }
  }

  console.log('[Main] No .env file found, using environment variables');
}

// Load .env before requiring other modules
loadEnvFile();

const redis = require('./redis');
const db = require('./db');
const { Worker, registerHandlers, QUEUE_NAMES, QUEUE_PRIORITY } = require('./queue');
const scheduler = require('./scheduler');

// Import task handlers
const accountCreation = require('./tasks/accountCreation');
const hostTasks = require('./tasks/hostTasks');
const bootstrapTasks = require('./tasks/bootstrapTasks');
const certificateTasks = require('./tasks/certificateTasks');
const cleanupTasks = require('./tasks/cleanupTasks');

let worker = null;
let shuttingDown = false;

/**
 * Parse --queue argument from command line
 * @returns {string[]|null} Array of queue names to consume, or null for all
 */
function parseQueueArg() {
  const args = process.argv.slice(2);
  const queueIndex = args.indexOf('--queue');

  if (queueIndex === -1) {
    return null; // All queues
  }

  const queueArg = args[queueIndex + 1];
  if (!queueArg) {
    console.error('[Main] --queue requires a value (comma-separated queue names)');
    process.exit(1);
  }

  const queueNames = queueArg.split(',').map((q) => q.trim());
  const validQueues = [];

  const queueMap = {
    hosts: QUEUE_NAMES.HOSTS,
    operations: QUEUE_NAMES.OPERATIONS,
    bootstrap: QUEUE_NAMES.BOOTSTRAP,
    certificates: QUEUE_NAMES.CERTIFICATES,
    default: QUEUE_NAMES.DEFAULT,
  };

  for (const name of queueNames) {
    const mapped = queueMap[name];
    if (mapped) {
      validQueues.push(mapped);
    } else {
      console.error(`[Main] Unknown queue name: ${name}`);
      console.error(`[Main] Valid queue names: ${Object.keys(queueMap).join(', ')}`);
      process.exit(1);
    }
  }

  return validQueues.length > 0 ? validQueues : null;
}

/**
 * Register all task handlers
 */
function registerAllHandlers() {
  registerHandlers(accountCreation.handlers);
  registerHandlers(hostTasks.handlers);
  registerHandlers(bootstrapTasks.handlers);
  registerHandlers(certificateTasks.handlers);
  registerHandlers(cleanupTasks.handlers);

  console.log('[Main] All task handlers registered');
}

/**
 * Graceful shutdown
 */
async function gracefulShutdown(signal) {
  if (shuttingDown) {
    console.log(`[Main] Already shutting down, ignoring ${signal}`);
    return;
  }

  shuttingDown = true;
  console.log(`[Main] Received ${signal}, shutting down gracefully...`);

  // Stop scheduler
  try {
    scheduler.stop();
  } catch (err) {
    console.error('[Main] Error stopping scheduler:', err.message);
  }

  // Stop worker
  if (worker) {
    try {
      await worker.stop();
    } catch (err) {
      console.error('[Main] Error stopping worker:', err.message);
    }
  }

  // Close connections
  try {
    await redis.disconnect();
  } catch (err) {
    console.error('[Main] Error disconnecting Redis:', err.message);
  }

  try {
    await db.close();
  } catch (err) {
    console.error('[Main] Error closing DB pool:', err.message);
  }

  console.log('[Main] Shutdown complete');
  process.exit(0);
}

/**
 * Main entry point
 */
async function main() {
  console.log('========================================');
  console.log('  2c2a Task Queue Worker v1.0.0');
  console.log('========================================');
  console.log(`[Main] PID: ${process.pid}`);
  console.log(`[Main] Node.js: ${process.version}`);
  console.log(`[Main] Started at: ${new Date().toISOString()}`);

  // Register all task handlers
  registerAllHandlers();

  // Determine which queues to consume
  const queues = parseQueueArg();
  if (queues) {
    console.log(`[Main] Consuming queues: ${queues.join(', ')}`);
  } else {
    console.log(`[Main] Consuming all queues (priority order): ${QUEUE_PRIORITY.join(', ')}`);
  }

  // Initialize Redis connection
  try {
    await redis.connect();
    console.log('[Main] Redis connected');
  } catch (err) {
    console.error('[Main] Failed to connect to Redis:', err.message);
    process.exit(1);
  }

  // Test DB connection
  try {
    const dbOk = await db.testConnection();
    if (dbOk) {
      console.log('[Main] Database connected');
    } else {
      console.error('[Main] Database connection test failed');
      process.exit(1);
    }
  } catch (err) {
    console.error('[Main] Failed to connect to database:', err.message);
    process.exit(1);
  }

  // Create and start worker
  worker = new Worker({
    queues: queues || QUEUE_PRIORITY,
  });

  try {
    await worker.start();
    console.log('[Main] Worker started');
  } catch (err) {
    console.error('[Main] Failed to start worker:', err.message);
    process.exit(1);
  }

  // Start scheduler
  try {
    scheduler.start();
    console.log('[Main] Scheduler started');
  } catch (err) {
    console.error('[Main] Failed to start scheduler:', err.message);
    // Non-fatal, continue without scheduler
  }

  console.log('[Main] Worker system is ready');
  console.log('========================================');

  // Register signal handlers for graceful shutdown
  process.on('SIGINT', () => gracefulShutdown('SIGINT'));
  process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));

  // Handle uncaught exceptions
  process.on('uncaughtException', (err) => {
    console.error('[Main] Uncaught exception:', err);
    gracefulShutdown('uncaughtException');
  });

  process.on('unhandledRejection', (reason) => {
    console.error('[Main] Unhandled rejection:', reason);
  });
}

// Run main
main().catch((err) => {
  console.error('[Main] Fatal error:', err);
  process.exit(1);
});
