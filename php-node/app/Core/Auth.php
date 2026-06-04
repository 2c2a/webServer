<?php

declare(strict_types=1);

namespace App\Core;

/**
 * 认证系统 - 登录/登出/权限检查
 */
class Auth
{
    private Session $session;
    private Database $database;

    /** @var array|null 当前用户数据缓存 */
    private ?array $userCache = null;

    public function __construct(Session $session, Database $database)
    {
        $this->session = $session;
        $this->database = $database;
    }

    /**
     * 登录用户 - 设置会话
     */
    public function login(array $user): void
    {
        $this->session->set('auth_user_id', (int) $user['id']);
        $this->session->set('auth_user_role', $user['role'] ?? 'user');
        $this->session->set('auth_login_time', time());

        // 重新生成 Session ID 防止固定攻击
        $this->session->regenerate();

        // 缓存用户数据
        $this->userCache = $user;
    }

    /**
     * 登出 - 清除会话
     */
    public function logout(): void
    {
        $this->session->remove('auth_user_id');
        $this->session->remove('auth_user_role');
        $this->session->remove('auth_login_time');
        $this->userCache = null;

        $this->session->regenerate();
    }

    /**
     * 检查是否已登录
     */
    public function check(): bool
    {
        return $this->session->has('auth_user_id');
    }

    /**
     * 获取当前用户（从缓存或数据库）
     */
    public function user(): ?array
    {
        if (!$this->check()) {
            return null;
        }

        if ($this->userCache !== null) {
            return $this->userCache;
        }

        $userId = $this->id();
        if ($userId === null) {
            return null;
        }

        $user = $this->database->fetch(
            'SELECT * FROM "user" WHERE id = :id AND is_active = true',
            [':id' => $userId]
        );

        if ($user === null) {
            $this->logout();
            return null;
        }

        $this->userCache = $user;
        return $user;
    }

    /**
     * 获取当前用户 ID
     */
    public function id(): ?int
    {
        $userId = $this->session->get('auth_user_id');
        return $userId !== null ? (int) $userId : null;
    }

    /**
     * 尝试验证用户凭据
     *
     * @return array|null 成功返回用户数据，失败返回 null
     */
    public function attempt(string $username, string $password): ?array
    {
        // 支持用户名或邮箱登录
        $user = $this->database->fetch(
            'SELECT * FROM "user" WHERE (username = :username OR email = :email) AND is_active = true',
            [':username' => $username, ':email' => $username]
        );

        if ($user === null) {
            return null;
        }

        if (!$this->verifyPassword($password, $user['password'])) {
            return null;
        }

        return $user;
    }

    /**
     * 密码哈希
     */
    public function hashPassword(string $password): string
    {
        $algo = match (PASSWORD_ALGO) {
            'argon2i'  => PASSWORD_ARGON2I,
            'argon2id' => PASSWORD_ARGON2ID,
            default    => PASSWORD_BCRYPT,
        };

        $options = [];
        if ($algo === PASSWORD_BCRYPT) {
            $options['cost'] = PASSWORD_COST;
        }

        return password_hash($password, $algo, $options);
    }

    /**
     * 验证密码
     */
    public function verifyPassword(string $password, string $hash): bool
    {
        return password_verify($password, $hash);
    }

    /**
     * 检查密码是否需要重新哈希
     */
    public function needsRehash(string $hash): bool
    {
        $algo = match (PASSWORD_ALGO) {
            'argon2i'  => PASSWORD_ARGON2I,
            'argon2id' => PASSWORD_ARGON2ID,
            default    => PASSWORD_BCRYPT,
        };

        $options = [];
        if ($algo === PASSWORD_BCRYPT) {
            $options['cost'] = PASSWORD_COST;
        }

        return password_needs_rehash($hash, $algo, $options);
    }

    /**
     * 要求登录 - 未登录则重定向
     */
    public function requireAuth(): void
    {
        if (!$this->check()) {
            $loginUrl = '/accounts/login';
            if (isset($_SERVER['REQUEST_URI'])) {
                $loginUrl .= '?next=' . urlencode($_SERVER['REQUEST_URI']);
            }

            if ($this->isAjaxRequest()) {
                http_response_code(401);
                header('Content-Type: application/json');
                echo json_encode(['error' => true, 'message' => '请先登录']);
                exit;
            }

            http_response_code(302);
            header("Location: {$loginUrl}");
            exit;
        }
    }

    /**
     * 要求管理员权限 - 非管理员则重定向
     */
    public function requireAdmin(): void
    {
        $this->requireAuth();

        $user = $this->user();
        if ($user === null || ($user['role'] ?? '') !== 'admin') {
            if ($this->isAjaxRequest()) {
                http_response_code(403);
                header('Content-Type: application/json');
                echo json_encode(['error' => true, 'message' => '权限不足']);
                exit;
            }

            http_response_code(302);
            header('Location: /');
            exit;
        }
    }

    /**
     * 检查是否是站点组管理员
     */
    public function isSiteGroupAdmin(int $siteGroupId): bool
    {
        $userId = $this->id();
        if ($userId === null) {
            return false;
        }

        // 全局管理员
        $user = $this->user();
        if ($user !== null && ($user['role'] ?? '') === 'admin') {
            return true;
        }

        // 检查站点组管理员关系
        $relation = $this->database->fetch(
            'SELECT 1 FROM site_group_admin WHERE user_id = :user_id AND site_group_id = :sg_id',
            [':user_id' => $userId, ':sg_id' => $siteGroupId]
        );

        return $relation !== null;
    }

    /**
     * 获取用户角色
     */
    public function role(): string
    {
        return $this->session->get('auth_user_role', 'guest');
    }

    /**
     * 是否是管理员
     */
    public function isAdmin(): bool
    {
        return $this->role() === 'admin';
    }

    /**
     * 清除用户缓存
     */
    public function clearCache(): void
    {
        $this->userCache = null;
    }

    /**
     * 检查是否是 AJAX 请求
     */
    private function isAjaxRequest(): bool
    {
        return !empty($_SERVER['HTTP_X_REQUESTED_WITH'])
            && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) === 'xmlhttprequest';
    }
}
