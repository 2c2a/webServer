<?php

declare(strict_types=1);

namespace App\Core;

use Redis;
use RedisException;

/**
 * 会话管理 - Redis 存储 + 文件降级
 */
class Session
{
    private static ?Session $instance = null;

    private readonly string $sessionId;
    private readonly string $sessionName;

    /** @var array<string, mixed> 会话数据 */
    private array $data = [];

    /** @var bool 会话是否已启动 */
    private bool $started = false;

    /** @var array<string, mixed> Flash 消息 */
    private array $flash = [];

    /** @var array<string> 新设置的 flash 键 */
    private array $newFlash = [];

    /** @var Cache 缓存实例 */
    private Cache $cache;

    /** @var string 会话存储键前缀 */
    private readonly string $sessionPrefix;

    /** @var int 会话过期时间 */
    private readonly int $lifetime;

    private function __construct()
    {
        $this->sessionName = SESSION_NAME;
        $this->lifetime = SESSION_LIFETIME;
        $this->sessionPrefix = 'session:';
        $this->cache = Cache::getInstance();

        $this->start();
    }

    /**
     * 获取会话单例
     */
    public static function getInstance(): static
    {
        if (self::$instance === null) {
            self::$instance = new static();
        }
        return self::$instance;
    }

    /**
     * 启动会话
     */
    public function start(): void
    {
        if ($this->started) {
            return;
        }

        // 从 Cookie 获取或生成 Session ID
        if (isset($_COOKIE[$this->sessionName]) && $this->validateSessionId($_COOKIE[$this->sessionName])) {
            $this->sessionId = $_COOKIE[$this->sessionName];
        } else {
            $this->sessionId = $this->generateSessionId();
        }

        // 从存储加载会话数据
        $this->loadSession();

        // 加载 flash 数据
        $this->flash = $this->get('_flash', []);
        $this->set('_flash', []);

        $this->started = true;
    }

    /**
     * 获取会话值
     */
    public function get(string $key, mixed $default = null): mixed
    {
        return $this->data[$key] ?? $default;
    }

    /**
     * 设置会话值
     */
    public function set(string $key, mixed $value): void
    {
        $this->data[$key] = $value;
        $this->saveSession();
    }

    /**
     * 检查会话键是否存在
     */
    public function has(string $key): bool
    {
        return array_key_exists($key, $this->data);
    }

    /**
     * 删除会话键
     */
    public function remove(string $key): void
    {
        unset($this->data[$key]);
        $this->saveSession();
    }

    /**
     * 设置 Flash 消息（仅下次请求可用）
     */
    public function flash(string $key, mixed $value): void
    {
        $this->newFlash[$key] = $value;
        $flashData = $this->get('_flash', []);
        $flashData[$key] = $value;
        $this->set('_flash', $flashData);
    }

    /**
     * 获取 Flash 消息
     */
    public function getFlash(string $key, mixed $default = null): mixed
    {
        return $this->flash[$key] ?? $default;
    }

    /**
     * 设置会话过期时间
     */
    public function setExpiry(int $seconds): void
    {
        $this->saveSession(ttl: $seconds);
    }

    /**
     * 销毁会话
     */
    public function destroy(): void
    {
        // 从存储删除
        $cacheKey = $this->sessionPrefix . $this->sessionId;
        $this->cache->delete($cacheKey);

        // 清除数据
        $this->data = [];
        $this->flash = [];
        $this->newFlash = [];
        $this->started = false;

        // 删除 Cookie
        if (isset($_COOKIE[$this->sessionName])) {
            unset($_COOKIE[$this->sessionName]);
            setcookie(
                name: $this->sessionName,
                value: '',
                expires_or_options: time() - 3600,
                path: '/',
                secure: SESSION_COOKIE_SECURE,
                httponly: SESSION_COOKIE_HTTPONLY,
                samesite: SESSION_COOKIE_SAMESITE
            );
        }
    }

    /**
     * 重新生成 Session ID（防止会话固定攻击）
     */
    public function regenerate(): void
    {
        // 删除旧会话
        $oldKey = $this->sessionPrefix . $this->sessionId;
        $this->cache->delete($oldKey);

        // 生成新 ID
        $newId = $this->generateSessionId();

        // 更新 Cookie
        setcookie(
            name: $this->sessionName,
            value: $newId,
            expires_or_options: time() + $this->lifetime,
            path: '/',
            secure: SESSION_COOKIE_SECURE,
            httponly: SESSION_COOKIE_HTTPONLY,
            samesite: SESSION_COOKIE_SAMESITE
        );

        // 用新 ID 保存
        // 注意：sessionId 是 readonly，需要重建
        $this->data['_session_id'] = $newId;
        $this->saveSessionWithId($newId);
    }

    /**
     * 获取当前 Session ID
     */
    public function getId(): string
    {
        return $this->sessionId;
    }

    /**
     * 获取所有会话数据
     */
    public function all(): array
    {
        return $this->data;
    }

    /**
     * 从存储加载会话数据
     */
    private function loadSession(): void
    {
        $cacheKey = $this->sessionPrefix . $this->sessionId;
        $data = $this->cache->get($cacheKey);

        if ($data !== null && is_array($data)) {
            $this->data = $data;
        } else {
            $this->data = [];
        }

        // 设置 Cookie
        setcookie(
            name: $this->sessionName,
            value: $this->sessionId,
            expires_or_options: time() + $this->lifetime,
            path: '/',
            secure: SESSION_COOKIE_SECURE,
            httponly: SESSION_COOKIE_HTTPONLY,
            samesite: SESSION_COOKIE_SAMESITE
        );
    }

    /**
     * 保存会话数据到存储
     */
    private function saveSession(int $ttl = 0): void
    {
        $cacheKey = $this->sessionPrefix . $this->sessionId;
        $this->cache->set($cacheKey, $this->data, $ttl > 0 ? $ttl : $this->lifetime);
    }

    /**
     * 使用指定 ID 保存会话
     */
    private function saveSessionWithId(string $id, int $ttl = 0): void
    {
        $cacheKey = $this->sessionPrefix . $id;
        $this->cache->set($cacheKey, $this->data, $ttl > 0 ? $ttl : $this->lifetime);
    }

    /**
     * 生成安全的 Session ID
     */
    private function generateSessionId(): string
    {
        return bin2hex(random_bytes(32));
    }

    /**
     * 验证 Session ID 格式
     */
    private function validateSessionId(string $id): bool
    {
        return preg_match('/^[a-f0-9]{64}$/', $id) === 1;
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
