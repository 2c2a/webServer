<?php

declare(strict_types=1);

namespace App\Core;

/**
 * 快速 URL 路由器 - 基于正则匹配
 */
class Router
{
    /** @var array<string, array> 已注册的路由 */
    private array $routes = [];

    /** @var array<string, string> 路由缓存（路径+方法 => 匹配结果） */
    private static array $matchCache = [];

    /**
     * 批量注册路由
     */
    public function registerRoutes(array $routes): void
    {
        foreach ($routes as $route) {
            $this->add(
                method: $route['method'],
                path: $route['path'],
                controller: $route['controller'],
                action: $route['action'],
                middleware: $route['middleware'] ?? []
            );
        }
    }

    /**
     * 添加单条路由
     */
    public function add(
        string $method,
        string $path,
        string $controller,
        string $action,
        array $middleware = []
    ): void {
        // 将路径模式转换为正则表达式
        $regex = $this->compilePath($path);

        $this->routes[] = [
            'method'     => strtoupper($method),
            'path'       => $path,
            'regex'      => $regex['regex'],
            'paramNames' => $regex['paramNames'],
            'controller' => $controller,
            'action'     => $action,
            'middleware'  => $middleware,
        ];
    }

    /**
     * 将路径模式编译为正则表达式
     *
     * /users/{id}/posts → #^/users/(?P<id>[^/]+)/posts$#
     */
    private function compilePath(string $path): array
    {
        $paramNames = [];

        // 匹配 {paramName} 模式
        $regex = preg_replace_callback(
            '/\{([a-zA-Z_][a-zA-Z0-9_]*)\}/',
            function (array $matches) use (&$paramNames): string {
                $paramNames[] = $matches[1];
                return '(?P<' . $matches[1] . '>[^/]+)';
            },
            $path
        );

        // 转义正则特殊字符（除了我们刚插入的命名捕获组）
        // 由于我们已经处理了 {} 参数，现在对整个路径做安全处理
        $regex = '#^' . $regex . '$#';

        return [
            'regex'      => $regex,
            'paramNames' => $paramNames,
        ];
    }

    /**
     * 匹配当前请求到路由
     *
     * @return array|null 匹配到的路由信息（含 params），未匹配返回 null
     */
    public function match(string $method, string $path): ?array
    {
        $method = strtoupper($method);
        $cacheKey = "{$method}:{$path}";

        // 检查缓存
        if (isset(self::$matchCache[$cacheKey])) {
            return self::$matchCache[$cacheKey];
        }

        // 规范化路径：去除尾部斜杠（根路径除外）
        if ($path !== '/' && str_ends_with($path, '/')) {
            $path = rtrim($path, '/');
        }

        foreach ($this->routes as $route) {
            // 检查 HTTP 方法
            if ($route['method'] !== $method) {
                continue;
            }

            // 正则匹配
            if (!preg_match($route['regex'], $path, $matches)) {
                continue;
            }

            // 提取命名参数
            $params = [];
            foreach ($route['paramNames'] as $name) {
                if (isset($matches[$name]) && $matches[$name] !== '') {
                    $params[$name] = $matches[$name];
                }
            }

            $result = [
                'method'     => $route['method'],
                'path'       => $route['path'],
                'controller' => $route['controller'],
                'action'     => $route['action'],
                'middleware'  => $route['middleware'],
                'params'     => $params,
            ];

            // 缓存匹配结果
            self::$matchCache[$cacheKey] = $result;

            return $result;
        }

        return null;
    }

    /**
     * 生成 URL（反向路由）
     *
     * @param string $name 路由标识（controller.action）
     * @param array $params 路由参数
     */
    public function url(string $name, array $params = []): string
    {
        [$controller, $action] = explode('.', $name, 2);

        foreach ($this->routes as $route) {
            if ($route['controller'] === $controller && $route['action'] === $action) {
                $url = $route['path'];
                foreach ($params as $key => $value) {
                    $url = str_replace("{{$key}}", (string) $value, $url);
                }
                return $url;
            }
        }

        return '/';
    }

    /**
     * 获取所有已注册路由
     */
    public function getRoutes(): array
    {
        return $this->routes;
    }

    /**
     * 清除匹配缓存
     */
    public static function clearCache(): void
    {
        self::$matchCache = [];
    }
}
