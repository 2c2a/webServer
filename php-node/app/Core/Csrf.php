<?php

declare(strict_types=1);

namespace App\Core;

/**
 * CSRF 保护
 */
class Csrf
{
    private Session $session;

    public function __construct(Session $session)
    {
        $this->session = $session;
    }

    /**
     * 生成 CSRF 令牌并存储到会话
     */
    public function generateToken(): string
    {
        $token = bin2hex(random_bytes(CSRF_TOKEN_LENGTH));
        $tokens = $this->session->get('csrf_tokens', []);

        // 限制令牌数量，防止会话膨胀
        if (count($tokens) > 10) {
            $tokens = array_slice($tokens, -5, null, true);
        }

        $tokens[$token] = time();
        $this->session->set('csrf_tokens', $tokens);

        return $token;
    }

    /**
     * 验证 CSRF 令牌
     */
    public function validateToken(string $token): bool
    {
        if (empty($token)) {
            return false;
        }

        $tokens = $this->session->get('csrf_tokens', []);

        if (!isset($tokens[$token])) {
            return false;
        }

        // 验证后删除令牌（一次性使用）
        unset($tokens[$token]);
        $this->session->set('csrf_tokens', $tokens);

        return true;
    }

    /**
     * 获取当前 CSRF 令牌（如不存在则生成）
     */
    public function token(): string
    {
        $tokens = $this->session->get('csrf_tokens', []);

        if (!empty($tokens)) {
            // 返回最近一个未过期的令牌
            $now = time();
            foreach (array_reverse($tokens, true) as $t => $time) {
                // 令牌有效期 2 小时
                if ($now - $time < 7200) {
                    return $t;
                }
            }
        }

        return $this->generateToken();
    }

    /**
     * 输出 CSRF 隐藏字段 HTML
     */
    public function field(): string
    {
        $token = $this->token();
        return '<input type="hidden" name="' . htmlspecialchars(CSRF_TOKEN_NAME, ENT_QUOTES, 'UTF-8')
            . '" value="' . htmlspecialchars($token, ENT_QUOTES, 'UTF-8') . '">';
    }

    /**
     * 清理过期令牌
     */
    public function cleanup(): void
    {
        $tokens = $this->session->get('csrf_tokens', []);
        $now = time();
        $maxAge = 7200; // 2 小时

        $tokens = array_filter($tokens, fn(int $time): bool => ($now - $time) < $maxAge);
        $this->session->set('csrf_tokens', $tokens);
    }
}
