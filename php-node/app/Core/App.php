<?php

declare(strict_types=1);

namespace App\Core;

use App\Core\Router;
use App\Core\Request;
use App\Core\Response;
use App\Core\Database;
use App\Core\Session;
use App\Core\Auth;
use App\Core\Cache;
use App\Core\Middleware;
use App\Core\Csrf;
use App\Core\RateLimit;
use App\Core\Template;

/**
 * 主应用类 - 核心容器与请求生命周期管理
 */
class App
{
    private static ?App $instance = null;

    /** @var array<string, object> 共享实例容器 */
    private array $container = [];

    private Router $router;
    private Request $request;
    private Response $response;
    private Session $session;
    private Auth $auth;
    private Database $database;
    private Cache $cache;
    private Csrf $csrf;
    private RateLimit $rateLimit;
    private Template $template;

    private function __construct()
    {
        // 加载配置
        require_once dirname(__DIR__) . '/Config/config.php';

        // 初始化核心组件
        $this->database = Database::getInstance();
        $this->cache = Cache::getInstance();
        $this->session = Session::getInstance();
        $this->csrf = new Csrf($this->session);
        $this->auth = new Auth($this->session, $this->database);
        $this->rateLimit = new RateLimit($this->cache);
        $this->template = new Template();
        $this->request = Request::createFromGlobals();
        $this->response = new Response();
        $this->router = new Router();

        // 注册共享实例
        $this->container = [
            Database::class   => $this->database,
            Cache::class      => $this->cache,
            Session::class    => $this->session,
            Auth::class       => $this->auth,
            Csrf::class       => $this->csrf,
            RateLimit::class  => $this->rateLimit,
            Template::class   => $this->template,
            Request::class    => $this->request,
            Response::class   => $this->response,
            Router::class     => $this->router,
        ];

        // 加载路由
        $routes = require dirname(__DIR__) . '/Config/routes.php';
        $this->router->registerRoutes($routes);
    }

    /**
     * 获取应用单例
     */
    public static function getInstance(): static
    {
        if (self::$instance === null) {
            self::$instance = new static();
        }
        return self::$instance;
    }

    /**
     * 从容器获取实例
     */
    public function get(string $key): ?object
    {
        return $this->container[$key] ?? null;
    }

    /**
     * 向容器注册实例
     */
    public function set(string $key, object $instance): void
    {
        $this->container[$key] = $instance;
    }

    /**
     * 静态快捷方式：从容器获取实例
     */
    public static function resolve(string $key): ?object
    {
        return self::getInstance()->get($key);
    }

    /**
     * 运行应用 - 处理请求并返回响应
     */
    public function run(): void
    {
        try {
            $this->handleRequest();
        } catch (\Throwable $e) {
            $this->handleException($e);
        }
    }

    /**
     * 处理请求
     */
    private function handleRequest(): void
    {
        $method = $this->request->getMethod();
        $path = $this->request->getPath();

        // 匹配路由
        $route = $this->router->match($method, $path);

        if ($route === null) {
            $this->response->html(
                $this->template->render('errors/404', [
                    'message' => '页面未找到',
                ]),
                404
            )->send();
            return;
        }

        // 运行中间件管道
        $middlewareList = $route['middleware'] ?? [];
        $handler = function (Request $request) use ($route): Response {
            return $this->dispatchRoute($route, $request);
        };

        $pipeline = new Middleware($middlewareList, $this->auth, $this->csrf, $this->rateLimit, $this->session);
        $response = $pipeline->handle($this->request, $handler);

        $response->send();
    }

    /**
     * 分发路由到控制器方法
     */
    private function dispatchRoute(array $route, Request $request): Response
    {
        $controllerName = $route['controller'];
        $actionName = $route['action'];
        $params = $route['params'] ?? [];

        // 控制器类名映射
        $controllerClass = "\\App\\Controller\\{$controllerName}";

        if (!class_exists($controllerClass)) {
            return $this->response->html(
                $this->template->render('errors/500', [
                    'message' => "控制器 {$controllerName} 不存在",
                ]),
                500
            );
        }

        $controller = new $controllerClass(
            $this->request,
            $this->response,
            $this->database,
            $this->session,
            $this->auth,
            $this->cache,
            $this->template,
            $this->csrf
        );

        if (!method_exists($controller, $actionName)) {
            return $this->response->html(
                $this->template->render('errors/500', [
                    'message' => "方法 {$controllerName}::{$actionName} 不存在",
                ]),
                500
            );
        }

        // 调用控制器方法，传入路由参数
        $result = $controller->{$actionName}(...$params);

        // 如果控制器返回 Response 对象，直接使用
        if ($result instanceof Response) {
            return $result;
        }

        // 否则包装为 HTML 响应
        if (is_string($result)) {
            return $this->response->html($result);
        }

        if (is_array($result)) {
            return $this->response->json($result);
        }

        return $this->response;
    }

    /**
     * 异常处理
     */
    private function handleException(\Throwable $e): void
    {
        // 记录日志
        $this->logError($e);

        $code = $e->getCode() >= 400 && $e->getCode() < 600 ? $e->getCode() : 500;

        if ($this->request->isAjax()) {
            $this->response->json([
                'error' => true,
                'message' => APP_DEBUG ? $e->getMessage() : '服务器内部错误',
                'file' => APP_DEBUG ? $e->getFile() : null,
                'line' => APP_DEBUG ? $e->getLine() : null,
            ], $code)->send();
        } else {
            $this->response->html(
                $this->template->render('errors/500', [
                    'message' => APP_DEBUG ? $e->getMessage() : '服务器内部错误',
                    'file' => APP_DEBUG ? $e->getFile() : null,
                    'line' => APP_DEBUG ? $e->getLine() : null,
                    'trace' => APP_DEBUG ? $e->getTraceAsString() : null,
                ]),
                $code
            )->send();
        }
    }

    /**
     * 记录错误日志
     */
    private function logError(\Throwable $e): void
    {
        $logDir = LOG_PATH;
        if (!is_dir($logDir)) {
            @mkdir($logDir, 0755, true);
        }

        $logFile = $logDir . '/' . date('Y-m-d') . '.log';
        $message = sprintf(
            "[%s] %s: %s in %s:%d\nStack trace:\n%s\n",
            date('Y-m-d H:i:s'),
            get_class($e),
            $e->getMessage(),
            $e->getFile(),
            $e->getLine(),
            $e->getTraceAsString()
        );

        @file_put_contents($logFile, $message, FILE_APPEND | LOCK_EX);
    }

    /**
     * 获取各组件的快捷方法
     */
    public function getDatabase(): Database
    {
        return $this->database;
    }

    public function getCache(): Cache
    {
        return $this->cache;
    }

    public function getSession(): Session
    {
        return $this->session;
    }

    public function getAuth(): Auth
    {
        return $this->auth;
    }

    public function getCsrf(): Csrf
    {
        return $this->csrf;
    }

    public function getRateLimit(): RateLimit
    {
        return $this->rateLimit;
    }

    public function getTemplate(): Template
    {
        return $this->template;
    }

    public function getRequest(): Request
    {
        return $this->request;
    }

    public function getResponse(): Response
    {
        return $this->response;
    }

    public function getRouter(): Router
    {
        return $this->router;
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
