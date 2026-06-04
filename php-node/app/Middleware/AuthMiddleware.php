<?php

declare(strict_types=1);

namespace App\Middleware;

use App\Core\Request;
use App\Core\Response;
use App\Core\Auth;
use App\Core\Session;

/**
 * 认证中间件 - 检查用户是否已登录
 *
 * 未认证用户将被重定向到登录页面，AJAX 请求返回 401 JSON 响应
 */
class AuthMiddleware
{
    private Auth $auth;
    private Session $session;

    public function __construct(Auth $auth, Session $session)
    {
        $this->auth = $auth;
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
        if (!$this->auth->check()) {
            return $this->handleUnauthenticated($request);
        }

        return $next($request);
    }

    /**
     * 处理未认证请求
     */
    private function handleUnauthenticated(Request $request): Response
    {
        $response = new Response();

        // AJAX 请求返回 JSON
        if ($request->isAjax() || $request->expectsJson()) {
            return $response->json([
                'error'   => true,
                'message' => '请先登录',
            ], 401);
        }

        // 普通请求重定向到登录页
        $loginUrl = '/accounts/login';
        $currentPath = $request->getPath();

        // 保存当前路径作为登录后跳转目标
        if ($currentPath !== '/accounts/logout') {
            $loginUrl .= '?next=' . urlencode($request->getFullUrl());
        }

        return $response->redirect($loginUrl);
    }
}
