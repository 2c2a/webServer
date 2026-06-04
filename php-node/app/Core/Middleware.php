<?php

declare(strict_types=1);

namespace App\Core;

use App\Core\Request;
use App\Core\Response;

/**
 * 中间件管道 - 按顺序执行中间件链
 */
class Middleware
{
    /** @var array<string> 中间件名称列表 */
    private readonly array $middlewareNames;

    private Auth $auth;
    private Csrf $csrf;
    private RateLimit $rateLimit;
    private Session $session;

    public function __construct(
        array $middlewareNames,
        Auth $auth,
        Csrf $csrf,
        RateLimit $rateLimit,
        Session $session
    ) {
        $this->middlewareNames = $middlewareNames;
        $this->auth = $auth;
        $this->csrf = $csrf;
        $this->rateLimit = $rateLimit;
        $this->session = $session;
    }

    /**
     * 处理请求通过中间件管道
     *
     * @param Request $request 请求对象
     * @param callable(Request): Response $handler 最终处理器
     */
    public function handle(Request $request, callable $handler): Response
    {
        // 构建中间件管道（从后往前包装）
        $pipeline = array_reduce(
            array_reverse($this->middlewareNames),
            fn(callable $next, string $name): callable => $this->wrapMiddleware($name, $next),
            $handler
        );

        return $pipeline($request);
    }

    /**
     * 将中间件名称包装为可调用的闭包
     */
    private function wrapMiddleware(string $name, callable $next): callable
    {
        return function (Request $request) use ($name, $next): Response {
            $middleware = $this->resolveMiddleware($name);
            return $middleware($request, $next);
        };
    }

    /**
     * 解析中间件名称为可调用的处理函数
     *
     * @return callable(Request, callable): Response
     */
    private function resolveMiddleware(string $name): callable
    {
        return match ($name) {
            'auth'    => new AuthCheck($this->auth),
            'csrf'    => new CsrfCheck($this->csrf, $this->session),
            'admin'   => new AdminCheck($this->auth),
            'rate'    => new RateLimitCheck($this->rateLimit, $this->session),
            'sitegroup' => new SiteGroupResolve($this->session, $this->auth),
            'demo'    => new DemoModeCheck(),
            default   => throw new \RuntimeException("未知中间件: {$name}"),
        };
    }
}

/**
 * 认证检查中间件
 */
class AuthCheck
{
    public function __construct(private readonly Auth $auth) {}

    public function __invoke(Request $request, callable $next): Response
    {
        $this->auth->requireAuth();
        return $next($request);
    }
}

/**
 * 管理员检查中间件
 */
class AdminCheck
{
    public function __construct(private readonly Auth $auth) {}

    public function __invoke(Request $request, callable $next): Response
    {
        $this->auth->requireAdmin();
        return $next($request);
    }
}

/**
 * CSRF 检查中间件
 */
class CsrfCheck
{
    public function __construct(
        private readonly Csrf $csrf,
        private readonly Session $session
    ) {}

    public function __invoke(Request $request, callable $next): Response
    {
        // 仅对 POST/PUT/DELETE 请求验证 CSRF
        if (in_array($request->getMethod(), ['POST', 'PUT', 'DELETE'], true)) {
            $token = $request->input(CSRF_TOKEN_NAME)
                ?? $request->getHeader('X-CSRF-TOKEN')
                ?? '';

            if (!$this->csrf->validateToken($token)) {
                $response = new Response();

                if ($request->isAjax()) {
                    return $response->json([
                        'error' => true,
                        'message' => 'CSRF 令牌验证失败，请刷新页面重试',
                    ], 419);
                }

                return $response->html(
                    '<html><body><h1>419 - 页面已过期</h1><p>CSRF 令牌验证失败，请返回并重试。</p>'
                    . '<a href="javascript:history.back()">返回上一页</a></body></html>',
                    419
                );
            }
        }

        return $next($request);
    }
}

/**
 * 速率限制中间件
 */
class RateLimitCheck
{
    public function __construct(
        private readonly RateLimit $rateLimit,
        private readonly Session $session
    ) {}

    public function __invoke(Request $request, callable $next): Response
    {
        if (!RATE_LIMIT_ENABLED) {
            return $next($request);
        }

        $key = 'rate:' . $request->getIp();
        $maxAttempts = RATE_LIMIT_API_MAX;
        $decaySeconds = RATE_LIMIT_API_DECAY;

        if ($this->rateLimit->tooManyAttempts($key, $maxAttempts, $decaySeconds)) {
            $retryAfter = $this->rateLimit->availableIn($key, $maxAttempts, $decaySeconds);
            $response = new Response();

            if ($request->isAjax()) {
                return $response->json([
                    'error' => true,
                    'message' => "请求过于频繁，请 {$retryAfter} 秒后重试",
                    'retry_after' => $retryAfter,
                ], 429);
            }

            return $response->html(
                '<html><body><h1>429 - 请求过于频繁</h1><p>请稍后再试。</p></body></html>',
                429
            );
        }

        $this->rateLimit->hit($key, $decaySeconds);

        return $next($request);
    }
}

/**
 * 站点组解析中间件
 */
class SiteGroupResolve
{
    public function __construct(
        private readonly Session $session,
        private readonly Auth $auth
    ) {}

    public function __invoke(Request $request, callable $next): Response
    {
        $host = $request->getHost();

        // 尝试从缓存获取站点组映射
        $cache = Cache::getInstance();
        $cacheKey = 'sitegroup:host:' . $host;

        $siteGroup = $cache->remember($cacheKey, 3600, function () use ($host): ?array {
            $db = Database::getInstance();
            return $db->fetch(
                'SELECT sg.* FROM site_group sg WHERE sg.domain = :domain AND sg.is_active = true',
                [':domain' => $host]
            );
        });

        if ($siteGroup !== null) {
            $this->session->set('current_site_group_id', (int) $siteGroup['id']);
            $this->session->set('current_site_group_name', $siteGroup['name']);
        }

        return $next($request);
    }
}

/**
 * 演示模式检查中间件
 */
class DemoModeCheck
{
    public function __invoke(Request $request, callable $next): Response
    {
        if (DEMO_MODE && in_array($request->getMethod(), ['POST', 'PUT', 'DELETE'], true)) {
            $response = new Response();

            // 允许登录和登出
            $path = $request->getPath();
            if (str_starts_with($path, '/accounts/login') || str_starts_with($path, '/accounts/logout')) {
                return $next($request);
            }

            if ($request->isAjax()) {
                return $response->json([
                    'error' => true,
                    'message' => '演示模式下不允许修改操作',
                ], 403);
            }

            return $response->html(
                '<html><body><h1>403 - 演示模式</h1><p>演示模式下不允许修改操作。</p></body></html>',
                403
            );
        }

        return $next($request);
    }
}
