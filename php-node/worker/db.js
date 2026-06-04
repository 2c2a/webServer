'use strict';

const { Pool } = require('pg');

let pool = null;

function getPool() {
  if (!pool) {
    pool = new Pool({
      host: process.env.DB_HOST || '127.0.0.1',
      port: parseInt(process.env.DB_PORT || '5432', 10),
      database: process.env.DB_NAME || '2c2a',
      user: process.env.DB_USER || 'postgres',
      password: process.env.DB_PASSWORD || '',
      max: 10,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 5000,
    });

    pool.on('error', (err) => {
      console.error('[DB] Unexpected pool error:', err.message);
    });

    pool.on('connect', () => {
      console.log('[DB] New client connected to pool');
    });

    pool.on('remove', () => {
      console.log('[DB] Client removed from pool');
    });
  }
  return pool;
}

/**
 * Execute a parameterized query
 * @param {string} text - SQL query
 * @param {Array} params - Query parameters
 * @returns {object} Query result
 */
async function query(text, params) {
  const p = getPool();
  const start = Date.now();
  try {
    const result = await p.query(text, params);
    const duration = Date.now() - start;
    if (duration > 1000) {
      console.warn(`[DB] Slow query (${duration}ms):`, text.substring(0, 100));
    }
    return result;
  } catch (err) {
    console.error('[DB] Query error:', err.message, '| SQL:', text.substring(0, 200));
    throw err;
  }
}

/**
 * Fetch a single row
 * @param {string} text - SQL query
 * @param {Array} params - Query parameters
 * @returns {object|null} Single row or null
 */
async function fetchOne(text, params) {
  const result = await query(text, params);
  return result.rows[0] || null;
}

/**
 * Fetch all rows
 * @param {string} text - SQL query
 * @param {Array} params - Query parameters
 * @returns {Array} Array of rows
 */
async function fetchAll(text, params) {
  const result = await query(text, params);
  return result.rows;
}

/**
 * Insert a row and return it
 * @param {string} table - Table name
 * @param {object} data - Key-value pairs to insert
 * @returns {object} Inserted row
 */
async function insert(table, data) {
  const keys = Object.keys(data);
  const values = Object.values(data);
  const placeholders = keys.map((_, i) => `$${i + 1}`).join(', ');
  const columns = keys.join(', ');

  const sql = `INSERT INTO ${table} (${columns}) VALUES (${placeholders}) RETURNING *`;
  const result = await query(sql, values);
  return result.rows[0];
}

/**
 * Update rows and return the updated row
 * @param {string} table - Table name
 * @param {object} data - Key-value pairs to update
 * @param {string} where - WHERE clause (without "WHERE")
 * @param {Array} whereParams - Parameters for WHERE clause
 * @returns {object|null} Updated row or null
 */
async function update(table, data, where, whereParams) {
  const keys = Object.keys(data);
  const values = Object.values(data);
  const offset = values.length;

  const setClause = keys.map((key, i) => `${key} = $${i + 1}`).join(', ');
  const whereClause = where.replace(/\$(\d+)/g, (match, num) => `$${parseInt(num, 10) + offset}`);

  const sql = `UPDATE ${table} SET ${setClause} WHERE ${whereClause} RETURNING *`;
  const allParams = values.concat(whereParams);
  const result = await query(sql, allParams);
  return result.rows[0] || null;
}

/**
 * Run a callback in a transaction
 * @param {Function} callback - Async callback that receives a client
 * @returns {*} Callback result
 */
async function transaction(callback) {
  const p = getPool();
  const client = await p.connect();
  try {
    await client.query('BEGIN');
    const result = await callback(client);
    await client.query('COMMIT');
    return result;
  } catch (err) {
    await client.query('ROLLBACK').catch(() => {});
    throw err;
  } finally {
    client.release();
  }
}

/**
 * Test database connection
 * @returns {boolean}
 */
async function testConnection() {
  try {
    const result = await query('SELECT 1 AS test');
    return result.rows[0].test === 1;
  } catch (err) {
    console.error('[DB] Connection test failed:', err.message);
    return false;
  }
}

/**
 * Close the pool
 */
async function close() {
  if (pool) {
    await pool.end();
    pool = null;
    console.log('[DB] Pool closed');
  }
}

module.exports = {
  getPool,
  query,
  fetchOne,
  fetchAll,
  insert,
  update,
  transaction,
  testConnection,
  close,
};
