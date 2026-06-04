<?php

declare(strict_types=1);

namespace App\Core;

/**
 * HTTP 响应
 */
class Response
{
    private int $statusCode = 200;
    private string $statusText = 'OK';
    private string $body = '';
    private array $headers = [];
    private array $cookies = [];

    private const STATUS_TEXTS = [
        200 => 'OK',
        201 => 'Created',
        204 => 'No Content',
        301 => 'Moved Permanently',
        302 => 'Found',
        304 => 'Not Modified',
        400 => 'Bad Request',
        401 => 'Unauthorized',
        403 => 'Forbidden',
        404 => 'Not Found',
        405 => 'Method Not Allowed',
        419 => 'Page Expired',
        422 => 'Unprocessable Entity',
        429 => 'Too Many Requests',
        500 => 'Internal Server Error',
        502 => 'Bad Gateway',
        503 => 'Service Unavailable',
    ];

    /**
     * 创建 HTML 响应
     */
    public function html(string $content, int $status = 200): static
    {
        $this->body = $content;
        $this->statusCode = $status;
        $this->statusText = self::STATUS_TEXTS[$status] ?? 'Unknown';
        $this->setHeader('Content-Type', 'text/html; charset=utf-8');

        return $this;
    }

    /**
     * 创建 JSON 响应
     */
    public function json(mixed $data, int $status = 200): static
    {
        $this->body = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        $this->statusCode = $status;
        $this->statusText = self::STATUS_TEXTS[$status] ?? 'Unknown';
        $this->setHeader('Content-Type', 'application/json; charset=utf-8');

        return $this;
    }

    /**
     * 创建重定向响应
     */
    public function redirect(string $url, int $status = 302): static
    {
        $this->statusCode = $status;
        $this->statusText = self::STATUS_TEXTS[$status] ?? 'Found';
        $this->setHeader('Location', $url);
        $this->body = '';

        return $this;
    }

    /**
     * 设置响应头
     */
    public function setHeader(string $name, string $value): static
    {
        $this->headers[$name] = $value;
        return $this;
    }

    /**
     * 设置 Cookie
     */
    public function setCookie(
        string $name,
        string $value,
        int $expires = 0,
        string $path = '/',
        bool $secure = false,
        bool $httpOnly = true,
        string $sameSite = 'Lax'
    ): static {
        $this->cookies[] = [
            'name'     => $name,
            'value'    => $value,
            'expires'  => $expires,
            'path'     => $path,
            'secure'   => $secure,
            'httpOnly' => $httpOnly,
            'sameSite' => $sameSite,
        ];

        return $this;
    }

    /**
     * 设置状态码
     */
    public function setStatusCode(int $code, string $text = ''): static
    {
        $this->statusCode = $code;
        $this->statusText = $text ?: (self::STATUS_TEXTS[$code] ?? 'Unknown');
        return $this;
    }

    /**
     * 获取状态码
     */
    public function getStatusCode(): int
    {
        return $this->statusCode;
    }

    /**
     * 获取响应体
     */
    public function getBody(): string
    {
        return $this->body;
    }

    /**
     * 设置响应体
     */
    public function setBody(string $body): static
    {
        $this->body = $body;
        return $this;
    }

    /**
     * 发送响应（输出头和内容）
     */
    public function send(): void
    {
        // 发送状态行
        http_response_code($this->statusCode);

        // 发送头
        foreach ($this->headers as $name => $value) {
            header("{$name}: {$value}");
        }

        // 发送 Cookie
        foreach ($this->cookies as $cookie) {
            setcookie(
                name: $cookie['name'],
                value: $cookie['value'],
                expires_or_options: $cookie['expires'],
                path: $cookie['path'],
                secure: $cookie['secure'],
                httponly: $cookie['httpOnly'],
                samesite: $cookie['sameSite']
            );
        }

        // 发送内容
        echo $this->body;
    }

    /**
     * 发送响应并终止脚本
     */
    public function sendAndExit(): never
    {
        $this->send();
        exit;
    }

    /**
     * 禁用浏览器缓存
     */
    public function noCache(): static
    {
        $this->setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
        $this->setHeader('Pragma', 'no-cache');
        $this->setHeader('Expires', 'Wed, 11 Jan 1984 05:00:00 GMT');

        return $this;
    }

    /**
     * 设置内容长度
     */
    public function setContentLength(): static
    {
        $this->setHeader('Content-Length', (string) strlen($this->body));
        return $this;
    }
}
