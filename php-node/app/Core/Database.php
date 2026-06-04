<?php

declare(strict_types=1);

namespace App\Core;

use PDO;
use PDOException;
use PDOStatement;

/**
 * PostgreSQL 数据库连接 - 基于 PDO 的单例模式
 */
class Database
{
    private static ?Database $instance = null;

    private ?PDO $pdo = null;

    /** @var int 当前事务嵌套层级 */
    private int $transactionLevel = 0;

    /** @var string 最后执行的 SQL（调试用） */
    private string $lastSql = '';

    /** @var array 最后执行的参数（调试用） */
    private array $lastParams = [];

    private function __construct()
    {
        $this->connect();
    }

    /**
     * 获取数据库单例
     */
    public static function getInstance(): static
    {
        if (self::$instance === null) {
            self::$instance = new static();
        }
        return self::$instance;
    }

    /**
     * 建立 PDO 连接
     */
    private function connect(): void
    {
        $dsn = sprintf(
            'pgsql:host=%s;port=%d;dbname=%s;options=--search_path=%s',
            DB_HOST,
            DB_PORT,
            DB_NAME,
            DB_SCHEMA
        );

        $options = [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES   => false,
            PDO::ATTR_PERSISTENT         => false,
            PDO::ATTR_STRINGIFY_FETCHES  => false,
        ];

        try {
            $this->pdo = new PDO($dsn, DB_USER, DB_PASS, $options);
        } catch (PDOException $e) {
            throw new \RuntimeException(
                sprintf('数据库连接失败: %s', $e->getMessage()),
                (int) $e->getCode(),
                $e
            );
        }
    }

    /**
     * 获取 PDO 实例
     */
    public function getPdo(): PDO
    {
        // 检查连接是否有效，断线重连
        try {
            $this->pdo?->query('SELECT 1');
        } catch (PDOException) {
            $this->connect();
        }

        return $this->pdo;
    }

    /**
     * 执行查询，返回 PDOStatement
     */
    public function query(string $sql, array $params = []): PDOStatement
    {
        $this->lastSql = $sql;
        $this->lastParams = $params;

        $stmt = $this->getPdo()->prepare($sql);
        $stmt->execute($params);

        return $stmt;
    }

    /**
     * 查询单行
     */
    public function fetch(string $sql, array $params = []): ?array
    {
        $stmt = $this->query($sql, $params);
        $result = $stmt->fetch();

        return $result !== false ? $result : null;
    }

    /**
     * 查询多行
     */
    public function fetchAll(string $sql, array $params = []): array
    {
        $stmt = $this->query($sql, $params);
        return $stmt->fetchAll();
    }

    /**
     * 查询单列值
     */
    public function fetchColumn(string $sql, array $params = [], int $column = 0): mixed
    {
        $stmt = $this->query($sql, $params);
        $result = $stmt->fetchColumn($column);

        return $result !== false ? $result : null;
    }

    /**
     * 插入数据
     *
     * @param string $table 表名
     * @param array $data 键值对数据
     * @return string|null 最后插入的 ID
     */
    public function insert(string $table, array $data): ?string
    {
        if (empty($data)) {
            throw new \InvalidArgumentException('插入数据不能为空');
        }

        $columns = array_keys($data);
        $placeholders = array_map(fn(string $col): string => ':' . $col, $columns);

        $sql = sprintf(
            'INSERT INTO %s (%s) VALUES (%s)',
            $this->quoteIdentifier($table),
            implode(', ', array_map(fn(string $c): string => $this->quoteIdentifier($c), $columns)),
            implode(', ', $placeholders)
        );

        $params = [];
        foreach ($data as $key => $value) {
            $params[':' . $key] = $value;
        }

        $this->query($sql, $params);

        // PostgreSQL 获取最后插入 ID
        $lastId = $this->fetchColumn(
            "SELECT currval(pg_get_serial_sequence('{$this->quoteIdentifier($table)}', 'id'))"
        );

        return $lastId;
    }

    /**
     * 更新数据
     *
     * @param string $table 表名
     * @param array $data 键值对数据
     * @param string $where WHERE 条件
     * @param array $whereParams WHERE 参数
     * @return int 影响行数
     */
    public function update(string $table, array $data, string $where, array $whereParams = []): int
    {
        if (empty($data)) {
            throw new \InvalidArgumentException('更新数据不能为空');
        }

        $setParts = [];
        $params = [];

        foreach ($data as $key => $value) {
            $paramKey = ':set_' . $key;
            $setParts[] = $this->quoteIdentifier($key) . ' = ' . $paramKey;
            $params[$paramKey] = $value;
        }

        $sql = sprintf(
            'UPDATE %s SET %s WHERE %s',
            $this->quoteIdentifier($table),
            implode(', ', $setParts),
            $where
        );

        $params = array_merge($params, $whereParams);

        $stmt = $this->query($sql, $params);
        return $stmt->rowCount();
    }

    /**
     * 删除数据
     *
     * @param string $table 表名
     * @param string $where WHERE 条件
     * @param array $params WHERE 参数
     * @return int 影响行数
     */
    public function delete(string $table, string $where, array $params = []): int
    {
        $sql = sprintf(
            'DELETE FROM %s WHERE %s',
            $this->quoteIdentifier($table),
            $where
        );

        $stmt = $this->query($sql, $params);
        return $stmt->rowCount();
    }

    /**
     * 开始事务
     */
    public function beginTransaction(): void
    {
        if ($this->transactionLevel === 0) {
            $this->getPdo()->beginTransaction();
        } else {
            $this->getPdo()->exec("SAVEPOINT lvl_{$this->transactionLevel}");
        }
        $this->transactionLevel++;
    }

    /**
     * 提交事务
     */
    public function commit(): void
    {
        $this->transactionLevel--;

        if ($this->transactionLevel === 0) {
            $this->getPdo()->commit();
        } else {
            $this->getPdo()->exec("RELEASE SAVEPOINT lvl_{$this->transactionLevel}");
        }
    }

    /**
     * 回滚事务
     */
    public function rollback(): void
    {
        $this->transactionLevel--;

        if ($this->transactionLevel === 0) {
            $this->getPdo()->rollBack();
        } else {
            $this->getPdo()->exec("ROLLBACK TO SAVEPOINT lvl_{$this->transactionLevel}");
        }
    }

    /**
     * 在事务中执行回调
     *
     * @template T
     * @param callable(): T $callback
     * @return T
     */
    public function transaction(callable $callback): mixed
    {
        $this->beginTransaction();

        try {
            $result = $callback();
            $this->commit();
            return $result;
        } catch (\Throwable $e) {
            $this->rollback();
            throw $e;
        }
    }

    /**
     * 检查是否在事务中
     */
    public function inTransaction(): bool
    {
        return $this->transactionLevel > 0;
    }

    /**
     * 引用标识符（表名、列名）
     */
    public function quoteIdentifier(string $identifier): string
    {
        // 不重复引用
        if (str_starts_with($identifier, '"') && str_ends_with($identifier, '"')) {
            return $identifier;
        }

        // 处理 schema.table 格式
        if (str_contains($identifier, '.')) {
            $parts = explode('.', $identifier);
            return implode('.', array_map(fn(string $p): string => '"' . $p . '"', $parts));
        }

        return '"' . $identifier . '"';
    }

    /**
     * 获取最后执行的 SQL
     */
    public function getLastSql(): string
    {
        return $this->lastSql;
    }

    /**
     * 获取最后执行的参数
     */
    public function getLastParams(): array
    {
        return $this->lastParams;
    }

    /**
     * 禁止克隆
     */
    private function __clone() {}

    /**
     * 禁止反序列化
     */
    public function __wakeup(): void
    {
        throw new \RuntimeException('不允许反序列化单例');
    }
}
