<?php

declare(strict_types=1);

namespace App\Controller;

use App\Core\Request;
use App\Core\Response;
use App\Core\Database;
use App\Core\Session;
use App\Core\Auth;
use App\Core\Cache;
use App\Core\Template;
use App\Core\Csrf;
use App\Core\Validator;
use App\Model\User;
use App\Model\Host;
use App\Model\Product;
use App\Model\CloudComputerUser;
use App\Model\AccountOpeningRequest;
use App\Model\SystemConfig;
use App\Model\AuditLog;
use App\Service\TaskQueue;
use App\Service\CryptoService;

/**
 * 运维控制器 - 账号开通、云桌面管理、任务管理
 */
class OperationController
{
    public function __construct(
        private Request $request,
        private Response $response,
        private Database $database,
        private Session $session,
        private Auth $auth,
        private Cache $cache,
        private Template $template,
        private Csrf $csrf
    ) {}

    /**
     * 开通请求列表
     */
    public function accountOpeningList(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);
        $siteGroupId = $this->session->get('current_site_group_id');

        $filters = [
            'status'     => $this->request->input('status', ''),
            'product_id' => $this->request->input('product_id', ''),
            'page'       => max(1, (int) $this->request->input('page', 1)),
        ];

        $filters['offset'] = ($filters['page'] - 1) * PAGE_SIZE;

        $requests = AccountOpeningRequest::getWithFilters(
            (int) $user['id'],
            $isStaff,
            $isSuperuser,
            $filters,
            $siteGroupId
        );

        $html = $this->template->render('operations/account_opening_list', [
            'user'         => $user,
            'requests'     => $requests,
            'filters'      => $filters,
            'isStaff'      => $isStaff,
            'isSuperuser'  => $isSuperuser,
            'csrfToken'    => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 创建开通请求表单
     */
    public function accountOpeningCreate(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $siteGroupId = $this->session->get('current_site_group_id');
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        $products = Product::getVisibleToUser(
            (int) $user['id'],
            $isStaff,
            $isSuperuser,
            $siteGroupId
        );

        $html = $this->template->render('operations/account_opening_create', [
            'user'      => $user,
            'products'  => $products,
            'csrfToken' => $this->csrf->token(),
            'error'     => $this->session->flash('error'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 确认开通请求（预检查）
     */
    public function accountOpeningConfirm(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $productId = (int) $this->request->input('product_id', 0);
        $username = trim($this->request->input('username', ''));
        $userFullname = trim($this->request->input('user_fullname', ''));
        $userEmail = trim($this->request->input('user_email', ''));

        $product = Product::find($productId);

        if ($product === null) {
            return $this->response->json(['success' => false, 'message' => '产品不存在'], 404);
        }

        // 检查是否已有云用户
        $existingCloudUser = Product::getUserCloudUser($productId, (int) $user['id']);
        if ($existingCloudUser !== null && ($product['limit_one_per_user'] ?? false)) {
            return $this->response->json([
                'success' => false,
                'message' => '您已拥有该产品的云桌面账号',
            ], 400);
        }

        // 检查是否有待处理的请求
        $pendingRequest = Product::getUserPendingRequest($productId, (int) $user['id']);
        if ($pendingRequest !== null) {
            return $this->response->json([
                'success' => false,
                'message' => '您已提交过该产品的开通请求，请等待处理',
            ], 400);
        }

        // 检查用户名是否已存在
        $existingUser = CloudComputerUser::findByProductAndUsername($productId, $username);
        if ($existingUser !== null) {
            return $this->response->json([
                'success' => false,
                'message' => '该用户名已存在',
            ], 400);
        }

        return $this->response->json([
            'success' => true,
            'data'    => [
                'product' => $product,
                'auto_approval' => $product['auto_approval'] ?? false,
            ],
        ]);
    }

    /**
     * 提交通勤请求
     */
    public function accountOpeningSubmit(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $productId = (int) $this->request->input('product_id', 0);
        $username = trim($this->request->input('username', ''));
        $userFullname = trim($this->request->input('user_fullname', ''));
        $userEmail = trim($this->request->input('user_email', ''));
        $userDescription = trim($this->request->input('user_description', ''));
        $contactPhone = trim($this->request->input('contact_phone', ''));

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['product_id', 'username', 'user_fullname', 'user_email']);
        $validator->rule('email', 'user_email');

        if (!$validator->validate()) {
            return $this->response->json([
                'success' => false,
                'message' => implode('; ', $validator->errors()),
            ], 400);
        }

        $product = Product::find($productId);

        if ($product === null) {
            return $this->response->json(['success' => false, 'message' => '产品不存在'], 404);
        }

        // 重复检查
        if ($product['limit_one_per_user'] ?? false) {
            $existingCloudUser = Product::getUserCloudUser($productId, (int) $user['id']);
            if ($existingCloudUser !== null) {
                return $this->response->json(['success' => false, 'message' => '您已拥有该产品的云桌面账号'], 400);
            }
        }

        $pendingRequest = Product::getUserPendingRequest($productId, (int) $user['id']);
        if ($pendingRequest !== null) {
            return $this->response->json(['success' => false, 'message' => '您已提交过开通请求'], 400);
        }

        // 创建请求
        $accountRequest = AccountOpeningRequest::create([
            'applicant_id'      => (int) $user['id'],
            'contact_email'     => $user['email'],
            'contact_phone'     => $contactPhone,
            'username'          => $username,
            'user_fullname'     => $userFullname,
            'user_email'        => $userEmail,
            'user_description'  => $userDescription,
            'target_product_id' => $productId,
        ]);

        AuditLog::log('account_opening_submitted', (int) $user['id'], null, [
            'request_id' => (int) $accountRequest['id'],
            'product_id' => $productId,
            'username'   => $username,
        ]);

        // 自动审批
        if ($product['auto_approval'] ?? false) {
            AccountOpeningRequest::approve((int) $accountRequest['id'], (int) $user['id'], '自动审批');
            $taskId = AccountOpeningRequest::dispatchCreationTask((int) $accountRequest['id']);

            return $this->response->json([
                'success' => true,
                'message' => '开通请求已自动审批，正在创建账号',
                'task_id' => $taskId,
            ]);
        }

        return $this->response->json([
            'success' => true,
            'message' => '开通请求已提交，等待审批',
        ]);
    }

    /**
     * 开通请求详情
     */
    public function accountOpeningDetail(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $request = AccountOpeningRequest::findWithDetails($id);

        if ($request === null) {
            $this->session->flash('error', '请求不存在');
            return redirect('/operations/account-openings');
        }

        // 权限检查
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser && (int) $request['applicant_id'] !== (int) $user['id']) {
            $this->session->flash('error', '权限不足');
            return redirect('/operations/account-openings');
        }

        $html = $this->template->render('operations/account_opening_detail', [
            'user'        => $user,
            'request'     => $request,
            'isStaff'     => $isStaff,
            'isSuperuser' => $isSuperuser,
            'csrfToken'   => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 云用户列表（管理员）
     */
    public function cloudUserList(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser) {
            $this->session->flash('error', '权限不足');
            return redirect('/dashboard');
        }

        $siteGroupId = $this->session->get('current_site_group_id');

        $filters = [
            'status'     => $this->request->input('status', ''),
            'product_id' => $this->request->input('product_id', ''),
            'username'   => $this->request->input('username', ''),
            'page'       => max(1, (int) $this->request->input('page', 1)),
        ];

        $filters['offset'] = ($filters['page'] - 1) * PAGE_SIZE;

        $cloudUsers = CloudComputerUser::getAllWithFilters($filters, $siteGroupId);

        $html = $this->template->render('operations/cloud_user_list', [
            'user'       => $user,
            'cloudUsers' => $cloudUsers,
            'filters'    => $filters,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 我的云桌面列表
     */
    public function myCloudComputers(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $siteGroupId = $this->session->get('current_site_group_id');

        $cloudUsers = CloudComputerUser::getForUser((int) $user['id'], $siteGroupId);

        $html = $this->template->render('operations/my_cloud_computers', [
            'user'       => $user,
            'cloudUsers' => $cloudUsers,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 我的云桌面详情
     */
    public function myCloudComputerDetail(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $cloudUser = CloudComputerUser::getWithProductAndHost($id);

        if ($cloudUser === null) {
            $this->session->flash('error', '云桌面不存在');
            return redirect('/operations/my-cloud-computers');
        }

        // 权限检查
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser && (int) $cloudUser['owner_id'] !== (int) $user['id']) {
            $this->session->flash('error', '权限不足');
            return redirect('/operations/my-cloud-computers');
        }

        $html = $this->template->render('operations/my_cloud_computer_detail', [
            'user'      => $user,
            'cloudUser' => $cloudUser,
            'csrfToken' => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 获取并销毁密码（一次性查看）
     */
    public function getPassword(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $password = CloudComputerUser::getAndBurnPassword($id, (int) $user['id']);

        if (empty($password)) {
            return $this->response->json(['success' => false, 'message' => '获取密码失败或无权限'], 400);
        }

        AuditLog::log('password_viewed', (int) $user['id'], null, ['cloud_user_id' => $id]);

        return $this->response->json([
            'success'  => true,
            'password' => $password,
        ]);
    }

    /**
     * 获取产品磁盘配置 JSON
     */
    public function productDiskConfig(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $product = Product::find($id);

        if ($product === null) {
            return $this->response->json(['error' => '产品不存在'], 404);
        }

        $diskConfig = [
            'enable_disk_quota'      => (bool) ($product['enable_disk_quota'] ?? false),
            'default_disk_quota'     => json_decode($product['default_disk_quota'] ?? '{}', true),
            'allow_extra_quota_disks' => json_decode($product['allow_extra_quota_disks'] ?? '[]', true),
        ];

        return $this->response->json($diskConfig);
    }

    /**
     * 派发磁盘信息查询任务
     */
    public function hostDiskInfo(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser) {
            return $this->response->json(['error' => '权限不足'], 403);
        }

        $host = Host::find($id);

        if ($host === null) {
            return $this->response->json(['error' => '主机不存在'], 404);
        }

        $taskQueue = new TaskQueue();
        $taskId = $taskQueue->dispatchDiskInfo($id, (int) $user['id']);

        return $this->response->json([
            'success' => true,
            'task_id' => $taskId,
        ]);
    }

    /**
     * 产品邀请页面
     */
    public function productInvite(string $token): Response
    {
        $inviteToken = Product::getInvitationToken($token);

        if ($inviteToken === null) {
            $this->session->flash('error', '邀请链接无效或已过期');
            return redirect('/dashboard');
        }

        $user = $this->auth->user();

        $html = $this->template->render('operations/product_invite', [
            'user'        => $user,
            'inviteToken' => $inviteToken,
            'csrfToken'   => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 接受产品邀请
     */
    public function productInvitePost(string $token): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            $this->session->flash('error', '请先登录');
            return redirect('/login');
        }

        $inviteToken = Product::getInvitationToken($token);

        if ($inviteToken === null) {
            $this->session->flash('error', '邀请链接无效或已过期');
            return redirect('/dashboard');
        }

        // 授予访问权限
        $granted = Product::grantAccess(
            (int) $user['id'],
            (int) $inviteToken['product_id'],
            (int) ($inviteToken['product_group_id'] ?? 0),
            (int) $inviteToken['id']
        );

        if ($granted) {
            // 使用邀请令牌
            Product::useInvitationToken((int) $inviteToken['id']);

            AuditLog::log('invite_accepted', (int) $user['id'], null, [
                'token_id'   => (int) $inviteToken['id'],
                'product_id' => (int) $inviteToken['product_id'],
            ]);

            $this->session->flash('success', '已获得产品访问权限');
        } else {
            $this->session->flash('error', '已拥有该产品的访问权限');
        }

        return redirect('/dashboard');
    }

    /**
     * 生成 RDP 连接文件
     */
    public function rdpConnect(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $cloudUser = CloudComputerUser::getWithProductAndHost($id);

        if ($cloudUser === null) {
            return $this->response->json(['error' => '云桌面不存在'], 404);
        }

        // 权限检查
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser && (int) $cloudUser['owner_id'] !== (int) $user['id']) {
            return $this->response->json(['error' => '权限不足'], 403);
        }

        // 确定连接地址
        $hostname = $cloudUser['display_hostname'] ?: $cloudUser['host_hostname'];
        $port = $cloudUser['product_rdp_port'] ?: $cloudUser['host_rdp_port'] ?: 3389;

        // 如果有隧道，使用隧道地址
        if (!empty($cloudUser['tunnel_token']) && $cloudUser['tunnel_status'] === 'connected') {
            $hostname = $cloudUser['tunnel_token'] . '.' . ($this->request->server('HTTP_HOST', 'localhost'));
            $port = 443;
        }

        // 生成 RDP 文件内容
        $rdpContent = $this->generateRdpFile($hostname, $port, $cloudUser['username']);

        AuditLog::log('rdp_connect', (int) $user['id'], (int) $cloudUser['product_id'], [
            'cloud_user_id' => $id,
            'hostname'      => $hostname,
        ]);

        // 返回 RDP 文件下载
        $this->response->html($rdpContent);
        $this->response->setHeader('Content-Type', 'application/x-rdp');
        $this->response->setHeader('Content-Disposition', 'attachment; filename="' . $cloudUser['username'] . '.rdp"');

        return $this->response;
    }

    /**
     * 任务列表
     */
    public function taskList(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser) {
            $this->session->flash('error', '权限不足');
            return redirect('/dashboard');
        }

        $tasks = $this->database->fetchAll(
            'SELECT * FROM async_tasks ORDER BY created_at DESC LIMIT 50'
        );

        $html = $this->template->render('operations/task_list', [
            'user'  => $user,
            'tasks' => $tasks,
        ]);

        return $this->response->html($html);
    }

    /**
     * 任务详情
     */
    public function taskDetail(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser) {
            $this->session->flash('error', '权限不足');
            return redirect('/dashboard');
        }

        $task = $this->database->fetch(
            'SELECT * FROM async_tasks WHERE id = :id',
            [':id' => $id]
        );

        if ($task === null) {
            $this->session->flash('error', '任务不存在');
            return redirect('/operations/tasks');
        }

        // 获取任务进度记录
        $progress = $this->database->fetchAll(
            'SELECT * FROM task_progress WHERE task_id = :task_id ORDER BY created_at ASC',
            [':task_id' => $task['task_id']]
        );

        $html = $this->template->render('operations/task_detail', [
            'user'     => $user,
            'task'     => $task,
            'progress' => $progress,
        ]);

        return $this->response->html($html);
    }

    /**
     * 获取任务进度 JSON
     */
    public function taskProgress(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $task = $this->database->fetch(
            'SELECT task_id FROM async_tasks WHERE id = :id',
            [':id' => $id]
        );

        if ($task === null) {
            return $this->response->json(['error' => '任务不存在'], 404);
        }

        $taskQueue = new TaskQueue();
        $progress = $taskQueue->getTaskProgress($task['task_id']);

        return $this->response->json($progress);
    }

    /**
     * 生成 RDP 文件内容
     */
    private function generateRdpFile(string $hostname, int $port, string $username): string
    {
        $lines = [
            'full address:s:' . $hostname . ':' . $port,
            'username:s:' . $username,
            'screen mode id:i:2',
            'use multimon:i:0',
            'desktopwidth:i:1920',
            'desktopheight:i:1080',
            'session bpp:i:32',
            'compression:i:1',
            'keyboardhook:i:2',
            'audiocapturemode:i:0',
            'videoplaybackmode:i:1',
            'connection type:i:7',
            'networkautodetect:i:1',
            'bandwidthautodetect:i:1',
            'displayconnectionbar:i:1',
            'enableworkspacereconnect:i:0',
            'disable wallpaper:i:0',
            'allow font smoothing:i:1',
            'allow desktop composition:i:1',
            'disable full window drag:i:0',
            'disable menu anims:i:0',
            'disable themes:i:0',
            'disable cursor setting:i:0',
            'bitmapcachepersistenable:i:1',
            'audiomode:i:0',
            'redirectprinters:i:0',
            'redirectcomports:i:0',
            'redirectsmartcards:i:0',
            'redirectclipboard:i:1',
            'redirectposdevices:i:0',
            'autoreconnection enabled:i:1',
            'authentication level:i:2',
            'prompt for credentials:i:0',
            'negotiate security layer:i:1',
            'remoteapplicationmode:i:0',
            'alternate shell:s:',
            'shell working directory:s:',
            'gatewayhostname:s:',
            'gatewayusagemethod:i:4',
            'gatewaycredentialssource:i:4',
            'gatewayprofileusagemethod:i:0',
            'promptcredentialonce:i:0',
            'use redirection server name:i:0',
        ];

        return implode("\r\n", $lines) . "\r\n";
    }
}
