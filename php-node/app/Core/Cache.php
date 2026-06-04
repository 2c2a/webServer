<?php

declare(strict_types=1);

namespace App\Core;

use Redis;
use RedisException;

/**
 * Redis 缓存 - 单例模式，支持键前缀
 */
class Cache
{
    private static ?Cache $instance = null;

    private ?Redis $redis = null;

    /** @var bool Redis 是否可用 */
    private bool $available = false;

    /** @var string 键前缀 */
    private readonly string $prefix;

    /** @var array<string, mixed> 内存缓存（Redis 不可用时的降级方案） */
    private array $memoryCache = [];

    private function __construct()
    {
        $this->prefix = REDIS_PREFIX;
        $this->connect();
    }

    /**
     * 获取缓存单例
     */
    public static function getInstance(): static
    {
        if (self::$instance === null) {
            self::$instance = new static();
        }
        return self::$instance;
    }

    /**
     * 连接 Redis
     */
    private function connect(): void
    {
        try {
            $this->redis = new Redis();

            $connected = $this->redis->connect(
                host: REDIS_HOST,
                port: REDIS_PORT,
                timeout: (float) REDIS_TIMEOUT
            );

            if (!$connected) {
                $this->available = false;
                return;
            }

            // 认证
            if (REDIS_PASSWORD !== '') {
                $this->redis->auth(REDIS_PASSWORD);
            }

            // 选择数据库
            if (REDIS_DATABASE > 0) {
                $this->redis->select(REDIS_DATABASE);
            }

            // 设置序列化
            $this->redis->setOption(Redis::OPT_SERIALIZER, Redis::SERIALIZER_JSON);
            $this->redis->setOption(Redis::OPT_PREFIX, $this->prefix);

            $this->available = true;
        } catch (RedisException) {
            $this->available = false;
            $this->redis = null;
        }
    }

    /**
     * 获取 Redis 实例
     */
    public function getRedis(): ?Redis
    {
        return $this->redis;
    }

    /**
     * Redis 是否可用
     */
    public function isAvailable(): bool
    {
        return $this->available;
    }

    /**
     * 获取缓存值
     */
    public function get(string $key): mixed
    {
        if ($this->available) {
            try {
                $value = $this->redis->get($key);
                return $value !== false ? $value : null;
            } catch (RedisException) {
                $this->available = false;
            }
        }

        // 降级到内存缓存
        if (isset($this->memoryCache[$key])) {
            $item = $this->memoryCache[$key];
            if ($item['expires'] === 0 || $item['expires'] > time()) {
                return $item['value'];
            }
            unset($this->memoryCache[$key]);
        }

        return null;
    }

    /**
     * 设置缓存值
     */
    public function set(string $key, mixed $value, int $ttl = 0): bool
    {
        if ($this->available) {
            try {
                if ($ttl > 0) {
                    return $this->redis->setex($key, $ttl, $value);
                }
                return $this->redis->set($key, $value);
            } catch (RedisException) {
                $this->available = false;
            }
        }

        // 降级到内存缓存
        $this->memoryCache[$key] = [
            'value'   => $value,
            'expires' => $ttl > 0 ? time() + $ttl : 0,
        ];

        return true;
    }

    /**
     * 删除缓存
     */
    public function delete(string $key): bool
    {
        if ($this->available) {
            try {
                return $this->redis->del($key) > 0;
            } catch (RedisException) {
                $this->available = false;
            }
        }

        unset($this->memoryCache[$key]);
        return true;
    }

    /**
     * 检查缓存是否存在
     */
    public function has(string $key): bool
    {
        if ($this->available) {
            try {
                return $this->redis->exists($key) > 0;
            } catch (RedisException) {
                $this->available = false;
            }
        }

        if (isset($this->memoryCache[$key])) {
            $item = $this->memoryCache[$key];
            if ($item['expires'] === 0 || $item['expires'] > time()) {
                return true;
            }
            unset($this->memoryCache[$key]);
        }

        return false;
    }

    /**
     * 获取或设置缓存（Remember 模式）
     *
     * @template T
     * @param string $key 缓存键
     * @param int $ttl 过期时间（秒）
     * @param callable(): T $callback 回调函数
     * @return T
     */
    public function remember(string $key, int $ttl, callable $callback): mixed
    {
        $value = $this->get($key);

        if ($value !== null) {
            return $value;
        }

        $value = $callback();
        $this->set($key, $value, $ttl);

        return $value;
    }

    /**
     * 清除所有带前缀的缓存
     */
    public function flush(): bool
    {
        if ($this->available) {
            try {
                // 使用 SCAN 遍历并删除带前缀的键
                $iterator = null;
                while (($keys = $this->redis->scan($iterator, '*')) !== false) {
                    if (!empty($keys)) {
                        $this->redis->del(...$keys);
                    }
                }
                return true;
            } catch (RedisException) {
                $this->available = false;
            }
        }

        $this->memoryCache = [];
        return true;
    }

    /**
     * 自增
     */
    public function increment(string $key, int $value = 1): int
    {
        if ($this->available) {
            try {
                return $this->redis->incrBy($key, $value);
            } catch (RedisException) {
                $this->available = false;
            }
        }

        $current = (int) ($this->memoryCache[$key]['value'] ?? 0);
        $new = $current + $value;
        $this->memoryCache[$key] = [
            'value'   => $new,
            'expires' => $this->memoryCache[$key]['expires'] ?? 0,
        ];
        return $new;
    }

    /**
     * 自减
     */
    public function decrement(string $key, int $value = 1): int
    {
        return $this->increment($key, -$value);
    }

    /**
     * 设置键过期时间
     */
    public function expire(string $key, int $seconds): bool
    {
        if ($this->available) {
            try {
                return $this->redis->expire($key, $seconds);
            } catch (RedisException) {
                $this->available = false;
            }
        }

        if (isset($this->memoryCache[$key])) {
            $this->memoryCache[$key]['expires'] = time() + $seconds;
            return true;
        }

        return false;
    }

    /**
     * 获取键的剩余生存时间
     */
    public function ttl(string $key): int
    {
        if ($this->available) {
            try {
                return $this->redis->ttl($key);
            } catch (RedisException) {
                $this->available = false;
            }
        }

        if (isset($this->memoryCache[$key])) {
            $item = $this->memoryCache[$key];
            if ($item['expires'] === 0) {
                return -1; // 永不过期
            }
            $remaining = $item['expires'] - time();
            return $remaining > 0 ? $remaining : -2;
        }

        return -2; // 键不存在
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
