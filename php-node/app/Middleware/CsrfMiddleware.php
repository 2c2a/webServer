<?php

declare(strict_types=1);

namespace App\Middleware;

use App\Core\Request;
use App\Core\Response;
use App\Core\Csrf;
use App\Core\Session;

/**
 * CSRF 保护中间件 - 验证 POST/PUT/DELETE 请求的 CSRF 令牌
 *
 * 跳过条件:
 * - GET/HEAD/OPTIONS 请求
 * - 带 X-Requested-With 头的 AJAX 请求
 */
class CsrfMiddleware
{
    private Csrf $csrf;
    private Session $session;

    public function __construct(Csrf $csrf, Session $session)
    {
        $this->csrf = $csrf;
        $this->session = $session;
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
        // 仅对 POST/PUT/DELETE 请求验证 CSRF
        if ($request->isSafeMethod()) {
            return $next($request);
        }

        // 跳过带 X-Requested-With 头的 AJAX 请求
        if ($request->getHeader('X-Requested-With') !== null) {
            return $next($request);
        }

        // 获取 CSRF 令牌
        $token = $this->getTokenFromRequest($request);

        // 验证令牌
        if (!$this->csrf->validateToken($token)) {
            return $this->handleInvalidToken($request);
        }

        return $next($request);
    }

    /**
     * 从请求中获取 CSRF 令牌
     */
    private function getTokenFromRequest(Request $request): string
    {
        // 1. 从表单字段获取
        $token = $request->input(CSRF_TOKEN_NAME);
        if (!empty($token)) {
            return $token;
        }

        // 2. 从请求头获取
        $headerToken = $request->getHeader('X-CSRF-TOKEN');
        if (!empty($headerToken)) {
            return $headerToken;
        }

        return '';
    }

    /**
     * 处理无效的 CSRF 令牌
     */
    private function handleInvalidToken(Request $request): Response
    {
        $response = new Response();

        // AJAX 请求返回 JSON
        if ($request->isAjax() || $request->expectsJson()) {
            return $response->json([
                'error'   => true,
                'message' => 'CSRF 令牌验证失败，请刷新页面重试',
            ], 419);
        }

        // 普通请求返回 419 页面
        return $response->html(
            '<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>419 - 页面已过期</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
    <div class="text-center">
        <h1 class="text-6xl font-bold text-amber-500 mb-4">419</h1>
        <p class="text-xl text-gray-600 mb-6">页面已过期</p>
        <p class="text-gray-500 mb-8">CSRF 令牌验证失败，请返回并重试。</p>
        <a href="javascript:history.back()" class="inline-block bg-blue-600 text-white px-6 py-3 rounded-lg hover:bg-blue-700 transition">
            返回上一页
        </a>
    </div>
</body>
</html>',
            419
        );
    }
}
