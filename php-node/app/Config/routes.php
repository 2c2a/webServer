<?php

declare(strict_types=1);

/**
 * 路由定义 - 映射 URL 到控制器方法
 *
 * 每条路由包含:
 *  - method:     HTTP 方法 (GET/POST/PUT/DELETE)
 *  - path:       URL 模式，支持命名参数 {id}, {token} 等
 *  - controller: 控制器类名
 *  - action:     控制器方法名
 *  - middleware:  中间件数组 (auth, csrf, admin 等)
 */

return [
    // ========================================================================
    // 首页
    // ========================================================================
    [
        'method'     => 'GET',
        'path'       => '/',
        'controller' => 'DashboardController',
        'action'     => 'index',
        'middleware'  => [],
    ],

    // ========================================================================
    // 账户相关
    // ========================================================================
    [
        'method'     => 'GET',
        'path'       => '/accounts/login',
        'controller' => 'AccountController',
        'action'     => 'login',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/login',
        'controller' => 'AccountController',
        'action'     => 'loginPost',
        'middleware'  => [],
    ],
    [
        'method'     => 'GET',
        'path'       => '/accounts/register',
        'controller' => 'AccountController',
        'action'     => 'register',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/register',
        'controller' => 'AccountController',
        'action'     => 'registerPost',
        'middleware'  => [],
    ],
    [
        'method'     => 'GET',
        'path'       => '/accounts/register/{token}',
        'controller' => 'AccountController',
        'action'     => 'registerByLink',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/register/{token}',
        'controller' => 'AccountController',
        'action'     => 'registerByLinkPost',
        'middleware'  => [],
    ],
    [
        'method'     => 'GET',
        'path'       => '/accounts/profile',
        'controller' => 'AccountController',
        'action'     => 'profile',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/profile',
        'controller' => 'AccountController',
        'action'     => 'profilePost',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/logout',
        'controller' => 'AccountController',
        'action'     => 'logout',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/email/send-code',
        'controller' => 'AccountController',
        'action'     => 'sendEmailCode',
        'middleware'  => [],
    ],
    [
        'method'     => 'GET',
        'path'       => '/accounts/forgot-password',
        'controller' => 'AccountController',
        'action'     => 'forgotPassword',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/forgot-password',
        'controller' => 'AccountController',
        'action'     => 'forgotPasswordPost',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/email/send-forgot-password-code',
        'controller' => 'AccountController',
        'action'     => 'sendForgotPasswordCode',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/api/avatar',
        'controller' => 'AccountController',
        'action'     => 'uploadAvatar',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/accounts/api/password/change',
        'controller' => 'AccountController',
        'action'     => 'changePassword',
        'middleware'  => ['auth'],
    ],

    // ========================================================================
    // 仪表盘
    // ========================================================================
    [
        'method'     => 'GET',
        'path'       => '/dashboard/api/stats',
        'controller' => 'DashboardController',
        'action'     => 'stats',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/dashboard/widget-config',
        'controller' => 'DashboardController',
        'action'     => 'widgetConfig',
        'middleware'  => ['auth', 'admin'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/dashboard/api/widget-config',
        'controller' => 'DashboardController',
        'action'     => 'widgetConfigSave',
        'middleware'  => ['auth', 'admin'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/dashboard/sitegroup',
        'controller' => 'DashboardController',
        'action'     => 'sitegroupList',
        'middleware'  => ['auth', 'admin'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/dashboard/sitegroup/create',
        'controller' => 'DashboardController',
        'action'     => 'sitegroupCreate',
        'middleware'  => ['auth', 'admin'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/dashboard/sitegroup/create',
        'controller' => 'DashboardController',
        'action'     => 'sitegroupCreatePost',
        'middleware'  => ['auth', 'admin'],
    ],

    // ========================================================================
    // 运维操作
    // ========================================================================
    [
        'method'     => 'GET',
        'path'       => '/operations/account-openings',
        'controller' => 'OperationController',
        'action'     => 'accountOpeningList',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/account-openings/create',
        'controller' => 'OperationController',
        'action'     => 'accountOpeningCreate',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/operations/account-openings/confirm',
        'controller' => 'OperationController',
        'action'     => 'accountOpeningConfirm',
        'middleware'  => ['auth', 'csrf'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/operations/account-openings/submit',
        'controller' => 'OperationController',
        'action'     => 'accountOpeningSubmit',
        'middleware'  => ['auth', 'csrf'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/account-openings/{id}',
        'controller' => 'OperationController',
        'action'     => 'accountOpeningDetail',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/cloud-users',
        'controller' => 'OperationController',
        'action'     => 'cloudUserList',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/my-cloud-computers',
        'controller' => 'OperationController',
        'action'     => 'myCloudComputers',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/my-cloud-computers/{id}',
        'controller' => 'OperationController',
        'action'     => 'myCloudComputerDetail',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/operations/my-cloud-computers/{id}/get-password',
        'controller' => 'OperationController',
        'action'     => 'getPassword',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/api/product/{id}/disk-config',
        'controller' => 'OperationController',
        'action'     => 'productDiskConfig',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/api/host/{id}/disk-info',
        'controller' => 'OperationController',
        'action'     => 'hostDiskInfo',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/invite/{token}',
        'controller' => 'OperationController',
        'action'     => 'productInvite',
        'middleware'  => [],
    ],
    [
        'method'     => 'POST',
        'path'       => '/operations/invite/{token}',
        'controller' => 'OperationController',
        'action'     => 'productInvitePost',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/rdp/connect/{id}',
        'controller' => 'OperationController',
        'action'     => 'rdpConnect',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/tasks',
        'controller' => 'OperationController',
        'action'     => 'taskList',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/tasks/{id}',
        'controller' => 'OperationController',
        'action'     => 'taskDetail',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/operations/tasks/{id}/progress',
        'controller' => 'OperationController',
        'action'     => 'taskProgress',
        'middleware'  => ['auth'],
    ],

    // ========================================================================
    // 工单系统
    // ========================================================================
    [
        'method'     => 'GET',
        'path'       => '/tickets',
        'controller' => 'TicketController',
        'action'     => 'list',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/tickets/create',
        'controller' => 'TicketController',
        'action'     => 'create',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/tickets/create',
        'controller' => 'TicketController',
        'action'     => 'createPost',
        'middleware'  => ['auth', 'csrf'],
    ],
    [
        'method'     => 'GET',
        'path'       => '/tickets/{id}',
        'controller' => 'TicketController',
        'action'     => 'detail',
        'middleware'  => ['auth'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/tickets/{id}/comment',
        'controller' => 'TicketController',
        'action'     => 'addComment',
        'middleware'  => ['auth', 'csrf'],
    ],
    [
        'method'     => 'POST',
        'path'       => '/tickets/{id}/status',
        'controller' => 'TicketController',
        'action'     => 'updateStatus',
        'middleware'  => ['auth', 'csrf'],
    ],
];
