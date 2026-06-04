<?php

declare(strict_types=1);

namespace App\Core;

/**
 * HTTP 请求封装
 */
class Request
{
    private readonly string $method;
    private readonly string $path;
    private readonly array $queryParams;
    private readonly array $postData;
    private readonly array $files;
    private readonly array $server;
    private readonly array $cookies;
    private readonly array $headers;

    public function __construct(
        string $method,
        string $path,
        array $queryParams = [],
        array $postData = [],
        array $files = [],
        array $server = [],
        array $cookies = [],
        array $headers = []
    ) {
        $this->method = strtoupper($method);
        $this->path = $path;
        $this->queryParams = $queryParams;
        $this->postData = $postData;
        $this->files = $files;
        $this->server = $server;
        $this->cookies = $cookies;
        $this->headers = $headers;
    }

    /**
     * 从 PHP 全局变量创建请求
     */
    public static function createFromGlobals(): static
    {
        $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
        $path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?? '/';
        $queryParams = $_GET;
        $postData = $_POST;
        $files = $_FILES;
        $server = $_SERVER;
        $cookies = $_COOKIE;

        // 收集 HTTP 头
        $headers = [];
        foreach ($_SERVER as $key => $value) {
            if (str_starts_with($key, 'HTTP_')) {
                $headerName = str_replace('_', '-', substr($key, 5));
                $headers[$headerName] = $value;
            }
        }

        // 处理 Content-Type 为 application/json 的请求体
        $contentType = $_SERVER['CONTENT_TYPE'] ?? $_SERVER['HTTP_CONTENT_TYPE'] ?? '';
        if (str_contains($contentType, 'application/json') && $method !== 'GET') {
            $body = file_get_contents('php://input');
            if (!empty($body)) {
                $json = json_decode($body, true);
                if (is_array($json)) {
                    $postData = array_merge($postData, $json);
                }
            }
        }

        // 处理 PUT/DELETE 请求的伪装方法
        if (isset($postData['_method'])) {
            $method = strtoupper($postData['_method']);
        }

        return new static(
            method: $method,
            path: $path,
            queryParams: $queryParams,
            postData: $postData,
            files: $files,
            server: $server,
            cookies: $cookies,
            headers: $headers
        );
    }

    /**
     * 获取 HTTP 方法
     */
    public function getMethod(): string
    {
        return $this->method;
    }

    /**
     * 获取请求路径
     */
    public function getPath(): string
    {
        return $this->path;
    }

    /**
     * 获取查询参数
     */
    public function getQueryParams(): array
    {
        return $this->queryParams;
    }

    /**
     * 获取 POST 数据
     */
    public function getPostData(): array
    {
        return $this->postData;
    }

    /**
     * 获取输入值（先从 POST，再从 GET）
     */
    public function input(string $key, mixed $default = null): mixed
    {
        if (array_key_exists($key, $this->postData)) {
            return $this->postData[$key];
        }

        if (array_key_exists($key, $this->queryParams)) {
            return $this->queryParams[$key];
        }

        return $default;
    }

    /**
     * 获取查询参数值
     */
    public function query(string $key, mixed $default = null): mixed
    {
        return $this->queryParams[$key] ?? $default;
    }

    /**
     * 获取 POST 值
     */
    public function post(string $key, mixed $default = null): mixed
    {
        return $this->postData[$key] ?? $default;
    }

    /**
     * 获取上传文件
     */
    public function file(string $key): ?array
    {
        return $this->files[$key] ?? null;
    }

    /**
     * 获取所有输入
     */
    public function all(): array
    {
        return array_merge($this->queryParams, $this->postData);
    }

    /**
     * 仅获取指定键的输入
     */
    public function only(array $keys): array
    {
        $all = $this->all();
        return array_intersect_key($all, array_flip($keys));
    }

    /**
     * 排除指定键的输入
     */
    public function except(array $keys): array
    {
        $all = $this->all();
        return array_diff_key($all, array_flip($keys));
    }

    /**
     * 检查输入键是否存在
     */
    public function has(string $key): bool
    {
        return array_key_exists($key, $this->postData) || array_key_exists($key, $this->queryParams);
    }

    /**
     * 检查输入键是否存在且非空
     */
    public function filled(string $key): bool
    {
        $value = $this->input($key);
        return $value !== null && $value !== '';
    }

    /**
     * 获取客户端 IP
     */
    public function getIp(): string
    {
        // 按优先级检查代理头
        $ipHeaders = [
            'HTTP_X_FORWARDED_FOR',
            'HTTP_X_REAL_IP',
            'HTTP_CF_CONNECTING_IP',
            'REMOTE_ADDR',
        ];

        foreach ($ipHeaders as $header) {
            $ip = $this->server[$header] ?? null;
            if ($ip !== null && $ip !== '') {
                // X-Forwarded-For 可能包含多个 IP
                if (str_contains($ip, ',')) {
                    $ips = array_map('trim', explode(',', $ip));
                    $ip = $ips[0];
                }
                return $ip;
            }
        }

        return '0.0.0.0';
    }

    /**
     * 获取 User-Agent
     */
    public function getUserAgent(): string
    {
        return $this->server['HTTP_USER_AGENT'] ?? '';
    }

    /**
     * 获取请求头
     */
    public function getHeader(string $name): ?string
    {
        $normalizedName = strtoupper(str_replace('-', '_', $name));
        return $this->headers[$normalizedName] ?? null;
    }

    /**
     * 获取所有请求头
     */
    public function getHeaders(): array
    {
        return $this->headers;
    }

    /**
     * 获取主机名（用于站点组解析）
     */
    public function getHost(): string
    {
        return $this->server['HTTP_HOST']
            ?? $this->server['SERVER_NAME']
            ?? 'localhost';
    }

    /**
     * 是否是 AJAX 请求
     */
    public function isAjax(): bool
    {
        return isset($this->headers['X_REQUESTED_WITH'])
            && strtolower($this->headers['X_REQUESTED_WITH']) === 'xmlhttprequest';
    }

    /**
     * 是否是 GET 请求
     */
    public function isGet(): bool
    {
        return $this->method === 'GET';
    }

    /**
     * 是否是 POST 请求
     */
    public function isPost(): bool
    {
        return $this->method === 'POST';
    }

    /**
     * 是否是 PUT 请求
     */
    public function isPut(): bool
    {
        return $this->method === 'PUT';
    }

    /**
     * 是否是 DELETE 请求
     */
    public function isDelete(): bool
    {
        return $this->method === 'DELETE';
    }

    /**
     * 是否是安全方法（GET/HEAD/OPTIONS）
     */
    public function isSafeMethod(): bool
    {
        return in_array($this->method, ['GET', 'HEAD', 'OPTIONS'], true);
    }

    /**
     * 是否期望 JSON 响应
     */
    public function expectsJson(): bool
    {
        return $this->isAjax()
            || str_contains($this->server['HTTP_ACCEPT'] ?? '', 'application/json');
    }

    /**
     * 获取请求体原始内容
     */
    public function getBody(): string
    {
        return file_get_contents('php://input');
    }

    /**
     * 获取 Cookie 值
     */
    public function cookie(string $key, mixed $default = null): mixed
    {
        return $this->cookies[$key] ?? $default;
    }

    /**
     * 获取 Referer
     */
    public function getReferer(): string
    {
        return $this->server['HTTP_REFERER'] ?? '';
    }

    /**
     * 是否是 HTTPS
     */
    public function isSecure(): bool
    {
        return (!empty($this->server['HTTPS']) && $this->server['HTTPS'] !== 'off')
            || ($this->server['SERVER_PORT'] ?? '') === '443'
            || ($this->server['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https';
    }

    /**
     * 获取完整 URL
     */
    public function getFullUrl(): string
    {
        $scheme = $this->isSecure() ? 'https' : 'http';
        $host = $this->getHost();
        $uri = $this->server['REQUEST_URI'] ?? '/';

        return "{$scheme}://{$host}{$uri}";
    }
}
