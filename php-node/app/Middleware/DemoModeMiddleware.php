<?php

declare(strict_types=1);

namespace App\Middleware;

use App\Core\Request;
use App\Core\Response;

/**
 * 演示模式中间件 - 在演示环境下限制修改操作
 *
 * 检查 2C2A_DEMO 环境变量，设置 is_demo_mode 标志，
 * 并阻止密码修改等敏感操作
 */
class DemoModeMiddleware
{
    /** @var bool 是否为演示模式 */
    private readonly bool $isDemoMode;

    /** @var array 演示模式下允许的 POST 路径 */
    private const ALLOWED_POST_PATHS = [
        '/accounts/login',
        '/accounts/logout',
    ];

    /** @var array 演示模式下阻止的操作关键词 */
    private const BLOCKED_OPERATIONS = [
        'password',
        'delete',
        'remove',
        'avatar',
    ];

    public function __construct()
    {
        $this->isDemoMode = envBool('2C2A_DEMO', false);
    }

    /**
     * 处理请求
     *
     * @param Request $request 请求对象
     * @param callable $next 下一个中间件/处理器
     * @return Response 响应对象
     */
    public function handle(Request $request, callable $next): Response
    {
        // 设置演示模式标志
        $request->attributes['is_demo_mode'] = $this->isDemoMode;

        // 非演示模式直接放行
        if (!$this->isDemoMode) {
            return $next($request);
        }

        // 安全方法（GET/HEAD/OPTIONS）直接放行
        if ($request->isSafeMethod()) {
            return $next($request);
        }

        // 检查是否为允许的路径
        $path = $request->getPath();
        foreach (self::ALLOWED_POST_PATHS as $allowedPath) {
            if (str_starts_with($path, $allowedPath)) {
                return $next($request);
            }
        }

        // 检查是否为阻止的操作
        if ($this->isBlockedOperation($path)) {
            return $this->handleBlocked($request);
        }

        return $next($request);
    }

    /**
     * 检查路径是否为被阻止的操作
     */
    private function isBlockedOperation(string $path): bool
    {
        $lowerPath = strtolower($path);

        foreach (self::BLOCKED_OPERATIONS as $keyword) {
            if (str_contains($lowerPath, $keyword)) {
                return true;
            }
        }

        return false;
    }

    /**
     * 处理被阻止的操作
     */
    private function handleBlocked(Request $request): Response
    {
        $response = new Response();

        // AJAX 请求返回 JSON
        if ($request->isAjax() || $request->expectsJson()) {
            return $response->json([
                'error'   => true,
                'message' => '演示模式下不允许此操作',
            ], 403);
        }

        // 普通请求返回 403 页面
        return $response->html(
            '<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>403 - 演示模式</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
    <div class="text-center">
        <div class="mb-6">
            <svg class="mx-auto h-16 w-16 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/>
            </svg>
        </div>
        <h1 class="text-4xl font-bold text-gray-800 mb-4">演示模式</h1>
        <p class="text-lg text-gray-600 mb-8">演示环境下不允许此操作</p>
        <a href="javascript:history.back()" class="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition">
            返回上一页
        </a>
    </div>
</body>
</html>',
            403
        );
    }
}
