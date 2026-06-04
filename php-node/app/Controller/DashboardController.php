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
use App\Model\SystemConfig;
use App\Model\AuditLog;

/**
 * 仪表盘控制器 - 主页、统计、站点组管理
 */
class DashboardController
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
     * 主仪表盘页面
     */
    public function index(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $siteGroupId = $this->session->get('current_site_group_id');
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        // 获取用户可见的产品
        $products = Product::getVisibleToUser(
            (int) $user['id'],
            $isStaff,
            $isSuperuser,
            $siteGroupId
        );

        // 获取产品组
        $productGroups = Product::getProductGroups($siteGroupId);

        // 获取用户站点组
        $siteGroups = User::getSiteGroups((int) $user['id']);

        // 获取可管理的站点组
        $adminableSiteGroups = User::getAdminableSiteGroups((int) $user['id']);

        // 获取仪表盘小部件配置
        $widgetConfig = $this->getWidgetConfig((int) $user['id']);

        $html = $this->template->render('dashboard/index', [
            'user'                => $user,
            'products'            => $products,
            'productGroups'       => $productGroups,
            'siteGroups'          => $siteGroups,
            'adminableSiteGroups' => $adminableSiteGroups,
            'widgetConfig'        => $widgetConfig,
            'csrfToken'           => $this->csrf->token(),
            'currentSiteGroupId'  => $siteGroupId,
        ]);

        return $this->response->html($html);
    }

    /**
     * 统计数据 API
     */
    public function stats(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['error' => '未登录'], 401);
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);
        $siteGroupId = $this->session->get('current_site_group_id');

        if (!$isStaff && !$isSuperuser) {
            return $this->response->json(['error' => '权限不足'], 403);
        }

        $stats = [
            'hosts' => $this->getHostStats($siteGroupId),
            'operations' => $this->getOperationStats($siteGroupId),
            'users' => $this->getUserStats($siteGroupId),
            'account_opening' => $this->getAccountOpeningStats($siteGroupId),
        ];

        return $this->response->json($stats);
    }

    /**
     * 小部件配置页面
     */
    public function widgetConfig(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $widgetConfig = $this->getWidgetConfig((int) $user['id']);

        $html = $this->template->render('dashboard/widget_config', [
            'user'         => $user,
            'widgetConfig' => $widgetConfig,
            'csrfToken'    => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 保存小部件配置
     */
    public function widgetConfigSave(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $config = $this->request->input('config', []);

        if (!is_array($config)) {
            return $this->response->json(['success' => false, 'message' => '配置格式错误'], 400);
        }

        $this->database->query(
            'INSERT INTO dashboard_widgets (user_id, widget_config) VALUES (:user_id, :config)
             ON CONFLICT (user_id) DO UPDATE SET widget_config = :config2',
            [
                ':user_id' => (int) $user['id'],
                ':config'  => json_encode($config, JSON_UNESCAPED_UNICODE),
                ':config2' => json_encode($config, JSON_UNESCAPED_UNICODE),
            ]
        );

        return $this->response->json(['success' => true, 'message' => '配置已保存']);
    }

    /**
     * 站点组列表
     */
    public function sitegroupList(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if ($isSuperuser) {
            $siteGroups = $this->database->fetchAll('SELECT * FROM site_groups ORDER BY name');
        } else {
            $siteGroups = User::getAdminableSiteGroups((int) $user['id']);
        }

        $html = $this->template->render('dashboard/sitegroup_list', [
            'user'       => $user,
            'siteGroups' => $siteGroups,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 创建站点组表单
     */
    public function sitegroupCreate(): Response
    {
        $user = $this->auth->user();

        if ($user === null || !($user['is_superuser'] ?? false)) {
            $this->session->flash('error', '权限不足');
            return redirect('/dashboard/sitegroup');
        }

        $html = $this->template->render('dashboard/sitegroup_create', [
            'user'      => $user,
            'csrfToken' => $this->csrf->token(),
            'error'     => $this->session->flash('error'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 保存新站点组
     */
    public function sitegroupCreatePost(): Response
    {
        $user = $this->auth->user();

        if ($user === null || !($user['is_superuser'] ?? false)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $name = trim($this->request->input('name', ''));
        $description = trim($this->request->input('description', ''));

        if (empty($name)) {
            $this->session->flash('error', '站点组名称不能为空');
            return redirect('/dashboard/sitegroup/create');
        }

        // 检查名称唯一性
        $existing = $this->database->fetch(
            'SELECT id FROM site_groups WHERE name = :name',
            [':name' => $name]
        );

        if ($existing !== null) {
            $this->session->flash('error', '站点组名称已存在');
            return redirect('/dashboard/sitegroup/create');
        }

        $this->database->insert('site_groups', [
            'name'        => $name,
            'description' => $description,
            'is_active'   => true,
        ]);

        $id = $this->database->fetchColumn("SELECT currval(pg_get_serial_sequence('site_groups', 'id'))");

        // 创建者自动成为管理员
        $this->database->insert('site_group_admins', [
            'user_id'       => (int) $user['id'],
            'site_group_id' => (int) $id,
        ]);

        AuditLog::log('sitegroup_created', (int) $user['id'], null, ['name' => $name, 'site_group_id' => (int) $id]);

        $this->session->flash('success', '站点组已创建');
        return redirect('/dashboard/sitegroup');
    }

    /**
     * 查看站点组详情
     */
    public function sitegroupDetail(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $siteGroup = $this->database->fetch(
            'SELECT * FROM site_groups WHERE id = :id',
            [':id' => $id]
        );

        if ($siteGroup === null) {
            $this->session->flash('error', '站点组不存在');
            return redirect('/dashboard/sitegroup');
        }

        // 检查权限
        if (!User::isSiteGroupAdmin((int) $user['id'], $id)) {
            $this->session->flash('error', '权限不足');
            return redirect('/dashboard/sitegroup');
        }

        // 获取站点组的主机名
        $hostnames = $this->database->fetchAll(
            'SELECT * FROM site_group_hostnames WHERE site_group_id = :sg_id ORDER BY hostname',
            [':sg_id' => $id]
        );

        // 获取站点组的管理员
        $admins = $this->database->fetchAll(
            'SELECT u.* FROM users u
             INNER JOIN site_group_admins sga ON sga.user_id = u.id
             WHERE sga.site_group_id = :sg_id',
            [':sg_id' => $id]
        );

        // 获取站点组的成员
        $members = $this->database->fetchAll(
            'SELECT u.* FROM users u
             INNER JOIN user_site_groups usg ON usg.user_id = u.id
             WHERE usg.site_group_id = :sg_id',
            [':sg_id' => $id]
        );

        $html = $this->template->render('dashboard/sitegroup_detail', [
            'user'       => $user,
            'siteGroup'  => $siteGroup,
            'hostnames'  => $hostnames,
            'admins'     => $admins,
            'members'    => $members,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 更新站点组
     */
    public function sitegroupUpdate(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null || !User::isSiteGroupAdmin((int) $user['id'], $id)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $name = trim($this->request->input('name', ''));
        $description = trim($this->request->input('description', ''));

        if (empty($name)) {
            return $this->response->json(['success' => false, 'message' => '名称不能为空'], 400);
        }

        $this->database->update('site_groups', [
            'name'        => $name,
            'description' => $description,
        ], 'id = :id', [':id' => $id]);

        AuditLog::log('sitegroup_updated', (int) $user['id'], null, ['site_group_id' => $id]);

        return $this->response->json(['success' => true, 'message' => '站点组已更新']);
    }

    /**
     * 删除站点组
     */
    public function sitegroupDelete(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null || !($user['is_superuser'] ?? false)) {
            return $this->response->json(['success' => false, 'message' => '仅超级管理员可删除站点组'], 403);
        }

        // 检查是否有关联数据
        $hostCount = (int) $this->database->fetchColumn(
            'SELECT COUNT(*) FROM hosts WHERE site_group_id = :sg_id',
            [':sg_id' => $id]
        );

        if ($hostCount > 0) {
            return $this->response->json([
                'success' => false,
                'message' => "该站点组下还有 {$hostCount} 台主机，无法删除",
            ], 400);
        }

        $this->database->delete('site_groups', 'id = :id', [':id' => $id]);

        AuditLog::log('sitegroup_deleted', (int) $user['id'], null, ['site_group_id' => $id]);

        return $this->response->json(['success' => true, 'message' => '站点组已删除']);
    }

    /**
     * 添加主机名到站点组
     */
    public function sitegroupAddHostname(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null || !User::isSiteGroupAdmin((int) $user['id'], $id)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $hostname = trim($this->request->input('hostname', ''));
        $siteName = trim($this->request->input('site_name', ''));
        $branding = $this->request->input('branding', []);

        if (empty($hostname)) {
            return $this->response->json(['success' => false, 'message' => '主机名不能为空'], 400);
        }

        try {
            $this->database->insert('site_group_hostnames', [
                'site_group_id' => $id,
                'hostname'      => $hostname,
                'site_name'     => $siteName,
                'branding'      => is_array($branding) ? json_encode($branding, JSON_UNESCAPED_UNICODE) : '{}',
            ]);
        } catch (\Throwable) {
            return $this->response->json(['success' => false, 'message' => '主机名已存在'], 400);
        }

        AuditLog::log('sitegroup_hostname_added', (int) $user['id'], null, [
            'site_group_id' => $id,
            'hostname'      => $hostname,
        ]);

        return $this->response->json(['success' => true, 'message' => '主机名已添加']);
    }

    /**
     * 从站点组移除主机名
     */
    public function sitegroupRemoveHostname(int $id, int $hostnameId): Response
    {
        $user = $this->auth->user();

        if ($user === null || !User::isSiteGroupAdmin((int) $user['id'], $id)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $this->database->delete('site_group_hostnames', 'id = :id AND site_group_id = :sg_id', [
            ':id' => $hostnameId,
            ':sg_id' => $id,
        ]);

        AuditLog::log('sitegroup_hostname_removed', (int) $user['id'], null, [
            'site_group_id' => $id,
            'hostname_id'   => $hostnameId,
        ]);

        return $this->response->json(['success' => true, 'message' => '主机名已移除']);
    }

    /**
     * 添加管理员到站点组
     */
    public function sitegroupAddAdmin(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null || !User::isSiteGroupAdmin((int) $user['id'], $id)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $targetUserId = (int) $this->request->input('user_id', 0);

        if ($targetUserId <= 0) {
            return $this->response->json(['success' => false, 'message' => '请指定用户'], 400);
        }

        $targetUser = User::find($targetUserId);

        if ($targetUser === null) {
            return $this->response->json(['success' => false, 'message' => '用户不存在'], 404);
        }

        try {
            $this->database->insert('site_group_admins', [
                'user_id'       => $targetUserId,
                'site_group_id' => $id,
            ]);
        } catch (\Throwable) {
            return $this->response->json(['success' => false, 'message' => '该用户已是管理员'], 400);
        }

        AuditLog::log('sitegroup_admin_added', (int) $user['id'], null, [
            'site_group_id' => $id,
            'target_user_id' => $targetUserId,
        ]);

        return $this->response->json(['success' => true, 'message' => '管理员已添加']);
    }

    /**
     * 从站点组移除管理员
     */
    public function sitegroupRemoveAdmin(int $id, int $userId): Response
    {
        $user = $this->auth->user();

        if ($user === null || !User::isSiteGroupAdmin((int) $user['id'], $id)) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        // 不能移除自己
        if ((int) $user['id'] === $userId) {
            return $this->response->json(['success' => false, 'message' => '不能移除自己'], 400);
        }

        $this->database->delete('site_group_admins', 'user_id = :uid AND site_group_id = :sg_id', [
            ':uid' => $userId,
            ':sg_id' => $id,
        ]);

        AuditLog::log('sitegroup_admin_removed', (int) $user['id'], null, [
            'site_group_id' => $id,
            'target_user_id' => $userId,
        ]);

        return $this->response->json(['success' => true, 'message' => '管理员已移除']);
    }

    /**
     * 获取小部件配置
     */
    private function getWidgetConfig(int $userId): array
    {
        $row = $this->database->fetch(
            'SELECT widget_config FROM dashboard_widgets WHERE user_id = :user_id',
            [':user_id' => $userId]
        );

        if ($row === null) {
            return [];
        }

        $config = $row['widget_config'];

        if (is_string($config)) {
            $config = json_decode($config, true);
        }

        return is_array($config) ? $config : [];
    }

    /**
     * 获取主机统计
     */
    private function getHostStats(?int $siteGroupId): array
    {
        $sql = 'SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = \'online\') AS online,
                    COUNT(*) FILTER (WHERE status = \'offline\') AS offline,
                    COUNT(*) FILTER (WHERE status = \'error\') AS error';
        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' FROM hosts WHERE site_group_id = :sg_id OR site_group_id IS NULL';
            $params[':sg_id'] = $siteGroupId;
        } else {
            $sql .= ' FROM hosts';
        }

        return $this->database->fetch($sql, $params) ?: [];
    }

    /**
     * 获取操作统计
     */
    private function getOperationStats(?int $siteGroupId): array
    {
        $sql = 'SELECT
                    COUNT(*) AS total_tasks,
                    COUNT(*) FILTER (WHERE status = \'pending\') AS pending,
                    COUNT(*) FILTER (WHERE status = \'processing\') AS processing,
                    COUNT(*) FILTER (WHERE status = \'completed\') AS completed,
                    COUNT(*) FILTER (WHERE status = \'failed\') AS failed';
        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' FROM async_tasks at2
                      INNER JOIN products p ON p.id = (SELECT target_product_id FROM account_opening_requests WHERE id = at2.id::text::int)
                      WHERE p.site_group_id = :sg_id OR p.site_group_id IS NULL';
            $params[':sg_id'] = $siteGroupId;
        } else {
            $sql .= ' FROM async_tasks at2';
        }

        return $this->database->fetch($sql, $params) ?: [];
    }

    /**
     * 获取用户统计
     */
    private function getUserStats(?int $siteGroupId): array
    {
        $sql = 'SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE is_active = true) AS active,
                    COUNT(*) FILTER (WHERE is_staff = true) AS staff,
                    COUNT(*) FILTER (WHERE is_superuser = true) AS superuser';
        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' FROM users u
                      INNER JOIN user_site_groups usg ON usg.user_id = u.id
                      WHERE usg.site_group_id = :sg_id';
            $params[':sg_id'] = $siteGroupId;
        } else {
            $sql .= ' FROM users u';
        }

        return $this->database->fetch($sql, $params) ?: [];
    }

    /**
     * 获取开通请求统计
     */
    private function getAccountOpeningStats(?int $siteGroupId): array
    {
        $sql = 'SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = \'pending\') AS pending,
                    COUNT(*) FILTER (WHERE status = \'approved\') AS approved,
                    COUNT(*) FILTER (WHERE status = \'completed\') AS completed,
                    COUNT(*) FILTER (WHERE status = \'failed\') AS failed';
        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' FROM account_opening_requests aor
                      INNER JOIN products p ON p.id = aor.target_product_id
                      WHERE p.site_group_id = :sg_id OR p.site_group_id IS NULL';
            $params[':sg_id'] = $siteGroupId;
        } else {
            $sql .= ' FROM account_opening_requests aor';
        }

        return $this->database->fetch($sql, $params) ?: [];
    }
}
