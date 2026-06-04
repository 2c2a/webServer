<?php

declare(strict_types=1);

namespace App\Core;

/**
 * 速率限制 - 基于 Redis
 */
class RateLimit
{
    private Cache $cache;

    public function __construct(Cache $cache)
    {
        $this->cache = $cache;
    }

    /**
     * 检查是否超过速率限制
     *
     * @param string $key 限制键
     * @param int $maxAttempts 最大尝试次数
     * @param int $decaySeconds 衰减时间（秒）
     * @return bool true=允许, false=超限
     */
    public function check(string $key, int $maxAttempts, int $decaySeconds): bool
    {
        return !$this->tooManyAttempts($key, $maxAttempts, $decaySeconds);
    }

    /**
     * 是否超过尝试次数
     */
    public function tooManyAttempts(string $key, int $maxAttempts, int $decaySeconds): bool
    {
        $attempts = $this->attempts($key);

        if ($attempts >= $maxAttempts) {
            return true;
        }

        return false;
    }

    /**
     * 记录一次尝试
     */
    public function hit(string $key, int $decaySeconds): int
    {
        $hitKey = "ratelimit:{$key}:hits";
        $timerKey = "ratelimit:{$key}:timer";

        $attempts = $this->cache->increment($hitKey);

        // 首次访问时设置过期时间
        if ($attempts === 1) {
            $this->cache->set($timerKey, time(), $decaySeconds);
            $this->cache->expire($hitKey, $decaySeconds);
        }

        return $attempts;
    }

    /**
     * 获取当前尝试次数
     */
    public function attempts(string $key): int
    {
        $hitKey = "ratelimit:{$key}:hits";
        $value = $this->cache->get($hitKey);

        return $value !== null ? (int) $value : 0;
    }

    /**
     * 获取距离可再次尝试的剩余秒数
     */
    public function availableIn(string $key, int $maxAttempts, int $decaySeconds): int
    {
        $timerKey = "ratelimit:{$key}:timer";
        $timer = $this->cache->get($timerKey);

        if ($timer === null) {
            return 0;
        }

        $elapsed = time() - (int) $timer;
        $remaining = $decaySeconds - $elapsed;

        return max(0, $remaining);
    }

    /**
     * 清除指定键的速率限制
     */
    public function clear(string $key): void
    {
        $this->cache->delete("ratelimit:{$key}:hits");
        $this->cache->delete("ratelimit:{$key}:timer");
    }

    /**
     * 获取剩余可用次数
     */
    public function remainingAttempts(string $key, int $maxAttempts): int
    {
        $attempts = $this->attempts($key);
        return max(0, $maxAttempts - $attempts);
    }
}
