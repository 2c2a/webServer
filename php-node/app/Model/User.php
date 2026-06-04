<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;

/**
 * 用户模型
 */
class User
{
    /**
     * 根据 ID 查找用户
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM users WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 根据用户名查找用户
     */
    public static function findByUsername(string $username): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM users WHERE username = :username',
            [':username' => $username]
        );
    }

    /**
     * 根据邮箱查找用户
     */
    public static function findByEmail(string $email): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM users WHERE email = :email',
            [':email' => $email]
        );
    }

    /**
     * 创建用户
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $db->insert('users', [
            'username'     => $data['username'],
            'password'     => $data['password'],
            'email'        => $data['email'],
            'first_name'   => $data['first_name'] ?? '',
            'last_name'    => $data['last_name'] ?? '',
            'phone'        => $data['phone'] ?? null,
            'is_verified'  => $data['is_verified'] ?? false,
            'is_active'    => $data['is_active'] ?? true,
            'is_staff'     => $data['is_staff'] ?? false,
            'is_superuser' => $data['is_superuser'] ?? false,
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('users', 'id'))");

        // 创建用户档案
        if ($id !== null) {
            $db->insert('user_profiles', [
                'user_id'  => (int) $id,
                'nickname' => $data['nickname'] ?? $data['username'],
            ]);
        }

        return self::find((int) $id);
    }

    /**
     * 更新用户
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'username', 'email', 'first_name', 'last_name', 'phone',
            'avatar', 'is_verified', 'is_active', 'is_staff', 'is_superuser',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('users', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 获取用户所属的组
     */
    public static function getGroups(int $userId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT g.*, gp.is_default, gp.description AS group_description, gp.auto_staff, gp.sort_order
             FROM auth_groups g
             INNER JOIN user_groups ug ON ug.group_id = g.id
             LEFT JOIN group_profiles gp ON gp.group_id = g.id
             WHERE ug.user_id = :user_id
             ORDER BY gp.sort_order, g.name',
            [':user_id' => $userId]
        );
    }

    /**
     * 获取用户所属的站点组
     */
    public static function getSiteGroups(int $userId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT sg.* FROM site_groups sg
             INNER JOIN user_site_groups usg ON usg.site_group_id = sg.id
             WHERE usg.user_id = :user_id AND sg.is_active = true
             ORDER BY sg.name',
            [':user_id' => $userId]
        );
    }

    /**
     * 检查用户是否是站点组管理员
     */
    public static function isSiteGroupAdmin(int $userId, int $siteGroupId): bool
    {
        $user = self::find($userId);

        if ($user !== null && ($user['is_superuser'] ?? false)) {
            return true;
        }

        $result = Database::getInstance()->fetch(
            'SELECT 1 FROM site_group_admins WHERE user_id = :user_id AND site_group_id = :sg_id',
            [':user_id' => $userId, ':sg_id' => $siteGroupId]
        );

        return $result !== null;
    }

    /**
     * 根据用户组自动同步 staff 状态
     */
    public static function syncStaffStatus(int $userId): void
    {
        $result = Database::getInstance()->fetch(
            'SELECT 1 FROM user_groups ug
             INNER JOIN group_profiles gp ON gp.group_id = ug.group_id
             WHERE ug.user_id = :user_id AND gp.auto_staff = true
             LIMIT 1',
            [':user_id' => $userId]
        );

        $shouldBeStaff = $result !== null;

        Database::getInstance()->update(
            'users',
            ['is_staff' => $shouldBeStaff],
            'id = :id',
            [':id' => $userId]
        );
    }

    /**
     * 获取用户可管理的站点组
     */
    public static function getAdminableSiteGroups(int $userId): array
    {
        $user = self::find($userId);

        // 超级管理员可管理所有站点组
        if ($user !== null && ($user['is_superuser'] ?? false)) {
            return Database::getInstance()->fetchAll(
                'SELECT * FROM site_groups WHERE is_active = true ORDER BY name'
            );
        }

        return Database::getInstance()->fetchAll(
            'SELECT sg.* FROM site_groups sg
             INNER JOIN site_group_admins sga ON sga.site_group_id = sg.id
             WHERE sga.user_id = :user_id AND sg.is_active = true
             ORDER BY sg.name',
            [':user_id' => $userId]
        );
    }

    /**
     * 更新最后登录信息
     */
    public static function updateLastLogin(int $userId, string $ip): void
    {
        $db = Database::getInstance();

        $db->update('users', ['last_login_ip' => $ip], 'id = :id', [':id' => $userId]);

        // 记录登录日志
        $db->insert('login_logs', [
            'user_id'    => $userId,
            'ip_address' => $ip,
            'status'     => 'success',
        ]);
    }

    /**
     * 记录登录失败
     */
    public static function logLoginFailure(?int $userId, string $ip, string $reason = ''): void
    {
        Database::getInstance()->insert('login_logs', [
            'user_id'        => $userId,
            'ip_address'     => $ip,
            'status'         => 'failed',
            'failure_reason' => $reason,
        ]);
    }

    /**
     * 将用户添加到组
     */
    public static function addToGroup(int $userId, int $groupId): bool
    {
        try {
            Database::getInstance()->insert('user_groups', [
                'user_id'  => $userId,
                'group_id' => $groupId,
            ]);
            return true;
        } catch (\Throwable) {
            return false;
        }
    }

    /**
     * 将用户添加到站点组
     */
    public static function addToSiteGroup(int $userId, int $siteGroupId): bool
    {
        try {
            Database::getInstance()->insert('user_site_groups', [
                'user_id'       => $userId,
                'site_group_id' => $siteGroupId,
            ]);
            return true;
        } catch (\Throwable) {
            return false;
        }
    }
}
