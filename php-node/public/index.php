<?php

/**
 * 2C2A 应用入口文件
 *
 * 所有请求通过此文件路由，由 Nginx rewrite 规则指向
 */

declare(strict_types=1);

// ============================================================================
// 自动加载器 - 将类名映射到文件路径
// ============================================================================
spl_autoload_register(function (string $class): void {
    // 处理 App 命名空间
    $prefix = 'App\\';
    $baseDir = dirname(__DIR__) . '/app/';

    // 检查类名是否以 App\ 开头
    if (!str_starts_with($class, $prefix)) {
        return;
    }

    // 去除命名空间前缀，获取相对类名
    $relativeClass = substr($class, strlen($prefix));

    // 将命名空间分隔符替换为目录分隔符
    $file = $baseDir . str_replace('\\', '/', $relativeClass) . '.php';

    if (file_exists($file)) {
        require_once $file;
    }
});

// ============================================================================
// 全局辅助函数
// ============================================================================
if (!function_exists('e')) {
    /**
     * HTML 转义快捷函数
     */
    function e(string $value): string
    {
        return htmlspecialchars($value, ENT_QUOTES | ENT_HTML5, 'UTF-8', true);
    }
}

if (!function_exists('redirect')) {
    /**
     * 重定向快捷函数
     */
    function redirect(string $url, int $status = 302): never
    {
        http_response_code($status);
        header("Location: {$url}");
        exit;
    }
}

if (!function_exists('json_response')) {
    /**
     * JSON 响应快捷函数
     */
    function json_response(mixed $data, int $status = 200): never
    {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
        exit;
    }
}

if (!function_exists('abort')) {
    /**
     * 中止请求并返回错误
     */
    function abort(int $code = 404, string $message = ''): never
    {
        http_response_code($code);

        $messages = [
            400 => 'Bad Request',
            401 => 'Unauthorized',
            403 => 'Forbidden',
            404 => 'Not Found',
            405 => 'Method Not Allowed',
            419 => 'Page Expired',
            429 => 'Too Many Requests',
            500 => 'Internal Server Error',
        ];

        $message = $message ?: ($messages[$code] ?? 'Error');

        echo "<html><body><h1>{$code} - {$message}</h1></body></html>";
        exit;
    }
}

if (!function_exists('asset')) {
    /**
     * 生成静态资源 URL
     */
    function asset(string $path): string
    {
        $baseUrl = defined('APP_URL') ? APP_URL : '';
        return rtrim($baseUrl, '/') . '/' . ltrim($path, '/');
    }
}

if (!function_exists('url')) {
    /**
     * 生成 URL
     */
    function url(string $path = ''): string
    {
        $baseUrl = defined('APP_URL') ? APP_URL : '';
        return rtrim($baseUrl, '/') . '/' . ltrim($path, '/');
    }
}

if (!function_exists('old')) {
    /**
     * 获取旧输入值
     */
    function old(string $key, mixed $default = ''): mixed
    {
        static $session = null;
        if ($session === null) {
            try {
                $session = \App\Core\Session::getInstance();
            } catch (\Throwable) {
                return $default;
            }
        }

        return $session->get('_old_input.' . $key, $default);
    }
}

if (!function_exists('csrf_field')) {
    /**
     * 生成 CSRF 字段 HTML
     */
    function csrf_field(): string
    {
        try {
            $session = \App\Core\Session::getInstance();
            $csrf = new \App\Core\Csrf($session);
            return $csrf->field();
        } catch (\Throwable) {
            return '';
        }
    }
}

if (!function_exists('csrf_token')) {
    /**
     * 获取 CSRF 令牌
     */
    function csrf_token(): string
    {
        try {
            $session = \App\Core\Session::getInstance();
            $csrf = new \App\Core\Csrf($session);
            return $csrf->token();
        } catch (\Throwable) {
            return '';
        }
    }
}

if (!function_exists('db')) {
    /**
     * 获取数据库实例
     */
    function db(): \App\Core\Database
    {
        return \App\Core\Database::getInstance();
    }
}

if (!function_exists('auth')) {
    /**
     * 获取认证实例
     */
    function auth(): \App\Core\Auth
    {
        static $instance = null;
        if ($instance === null) {
            $instance = new \App\Core\Auth(
                \App\Core\Session::getInstance(),
                \App\Core\Database::getInstance()
            );
        }
        return $instance;
    }
}

if (!function_exists('session')) {
    /**
     * 获取会话实例
     */
    function session(): \App\Core\Session
    {
        return \App\Core\Session::getInstance();
    }
}

if (!function_exists('cache')) {
    /**
     * 获取缓存实例
     */
    function cache(): \App\Core\Cache
    {
        return \App\Core\Cache::getInstance();
    }
}

if (!function_exists('template')) {
    /**
     * 获取模板实例
     */
    function template(): \App\Core\Template
    {
        return new \App\Core\Template();
    }
}

if (!function_exists('request')) {
    /**
     * 获取当前请求实例
     */
    function request(): \App\Core\Request
    {
        try {
            return \App\Core\App::getInstance()->getRequest();
        } catch (\Throwable) {
            return \App\Core\Request::createFromGlobals();
        }
    }
}

if (!function_exists('csrf')) {
    /**
     * 获取 CSRF 实例
     */
    function csrf(): \App\Core\Csrf
    {
        return new \App\Core\Csrf(\App\Core\Session::getInstance());
    }
}

if (!function_exists('back')) {
    /**
     * 重定向回上一页
     */
    function back(): never
    {
        $referer = $_SERVER['HTTP_REFERER'] ?? '/';
        redirect($referer);
    }
}

// ============================================================================
// 启动应用
// ============================================================================
try {
    $app = \App\Core\App::getInstance();
    $app->run();
} catch (\Throwable $e) {
    // 最后的兜底错误处理
    http_response_code(500);
    header('Content-Type: text/html; charset=utf-8');

    if (defined('APP_DEBUG') && APP_DEBUG) {
        echo '<html><body>';
        echo '<h1>500 - 服务器内部错误</h1>';
        echo '<p>' . htmlspecialchars($e->getMessage(), ENT_QUOTES, 'UTF-8') . '</p>';
        echo '<p>文件: ' . htmlspecialchars($e->getFile(), ENT_QUOTES, 'UTF-8') . ':' . $e->getLine() . '</p>';
        echo '<pre>' . htmlspecialchars($e->getTraceAsString(), ENT_QUOTES, 'UTF-8') . '</pre>';
        echo '</body></html>';
    } else {
        echo '<html><body><h1>500 - 服务器内部错误</h1><p>请稍后重试</p></body></html>';
    }
}
