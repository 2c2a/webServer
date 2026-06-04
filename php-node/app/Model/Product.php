<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;

/**
 * 产品模型
 */
class Product
{
    /**
     * 根据 ID 查找产品
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM products WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 获取所有产品
     */
    public static function all(): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT * FROM products ORDER BY name'
        );
    }

    /**
     * 创建产品
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $db->insert('products', [
            'name'                    => $data['name'],
            'description'             => $data['description'] ?? '',
            'display_name'            => $data['display_name'] ?? $data['name'],
            'display_description'     => $data['display_description'] ?? '',
            'product_group_id'        => $data['product_group_id'] ?? null,
            'host_id'                 => $data['host_id'],
            'site_group_id'           => $data['site_group_id'] ?? null,
            'rdp_port'                => $data['rdp_port'] ?? 3389,
            'display_hostname'        => $data['display_hostname'] ?? '',
            'is_available'            => $data['is_available'] ?? true,
            'auto_approval'           => $data['auto_approval'] ?? false,
            'visibility'              => $data['visibility'] ?? 'public',
            'limit_one_per_user'      => $data['limit_one_per_user'] ?? false,
            'enable_disk_quota'       => $data['enable_disk_quota'] ?? false,
            'enable_host_protection'  => $data['enable_host_protection'] ?? false,
            'default_disk_quota'      => $data['default_disk_quota'] ?? '{}',
            'allow_extra_quota_disks' => $data['allow_extra_quota_disks'] ?? '[]',
            'created_by_id'           => $data['created_by_id'] ?? null,
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('products', 'id'))");

        return self::find((int) $id);
    }

    /**
     * 更新产品
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'name', 'description', 'display_name', 'display_description',
            'product_group_id', 'host_id', 'site_group_id', 'rdp_port',
            'display_hostname', 'is_available', 'auto_approval', 'visibility',
            'limit_one_per_user', 'enable_disk_quota', 'enable_host_protection',
            'default_disk_quota', 'allow_extra_quota_disks',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('products', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 获取可用产品（按站点组过滤）
     */
    public static function getAvailable(?int $siteGroupId = null): array
    {
        $sql = 'SELECT p.*, h.name AS host_name, h.status AS host_status
                FROM products p
                LEFT JOIN hosts h ON h.id = p.host_id
                WHERE p.is_available = true AND p.visibility = :visibility';

        $params = [':visibility' => 'public'];

        if ($siteGroupId !== null) {
            $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        $sql .= ' ORDER BY p.name';

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 获取用户可见的产品（公开 + 授权 + 供应商创建）
     */
    public static function getVisibleToUser(int $userId, bool $isStaff, bool $isSuperuser, ?int $siteGroupId = null): array
    {
        $db = Database::getInstance();

        // 超级管理员/员工可见所有
        if ($isSuperuser || $isStaff) {
            $sql = 'SELECT p.*, h.name AS host_name, h.status AS host_status
                    FROM products p
                    LEFT JOIN hosts h ON h.id = p.host_id
                    WHERE p.is_available = true';

            $params = [];

            if ($siteGroupId !== null) {
                $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
                $params[':sg_id'] = $siteGroupId;
            }

            $sql .= ' ORDER BY p.name';

            return $db->fetchAll($sql, $params);
        }

        // 普通用户：公开 + 通过 token 授权 + 通过产品组授权 + 供应商创建
        $sql = 'SELECT DISTINCT p.*, h.name AS host_name, h.status AS host_status
                FROM products p
                LEFT JOIN hosts h ON h.id = p.host_id
                LEFT JOIN product_access_grants pag ON pag.product_id = p.id AND pag.user_id = :user_id1 AND pag.is_revoked = false
                LEFT JOIN product_access_grants pag2 ON pag2.product_group_id = p.product_group_id AND pag2.user_id = :user_id2 AND pag2.is_revoked = false
                LEFT JOIN host_providers hp ON hp.host_id = p.host_id AND hp.user_id = :user_id3
                WHERE p.is_available = true
                AND (
                    p.visibility = \'public\'
                    OR pag.id IS NOT NULL
                    OR pag2.id IS NOT NULL
                    OR hp.id IS NOT NULL
                )';

        $params = [
            ':user_id1' => $userId,
            ':user_id2' => $userId,
            ':user_id3' => $userId,
        ];

        if ($siteGroupId !== null) {
            $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        $sql .= ' ORDER BY p.name';

        return $db->fetchAll($sql, $params);
    }

    /**
     * 获取产品组
     */
    public static function getProductGroups(?int $siteGroupId = null): array
    {
        $sql = 'SELECT pg.*, 
                (SELECT COUNT(*) FROM products p WHERE p.product_group_id = pg.id AND p.is_available = true) AS product_count
                FROM product_groups pg
                WHERE pg.is_active = true';

        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' AND (pg.site_group_id = :sg_id OR pg.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        $sql .= ' ORDER BY pg.display_order, pg.name';

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 检查用户在此产品上是否有云用户
     */
    public static function getUserCloudUser(int $productId, int $userId): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT ccu.* FROM cloud_computer_users ccu
             WHERE ccu.product_id = :product_id AND ccu.owner_id = :user_id AND ccu.status = :status
             LIMIT 1',
            [':product_id' => $productId, ':user_id' => $userId, ':status' => 'active']
        );
    }

    /**
     * 检查用户是否有待处理的开通请求
     */
    public static function getUserPendingRequest(int $productId, int $userId): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM account_opening_requests
             WHERE target_product_id = :product_id AND applicant_id = :user_id
             AND status IN (:pending, :approved)
             ORDER BY created_at DESC
             LIMIT 1',
            [':product_id' => $productId, ':user_id' => $userId, ':pending' => 'pending', ':approved' => 'approved']
        );
    }

    /**
     * 获取产品的邀请令牌
     */
    public static function getInvitationToken(string $token): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT pit.*, p.name AS product_name, pg.name AS product_group_name
             FROM product_invitation_tokens pit
             INNER JOIN products p ON p.id = pit.product_id
             LEFT JOIN product_groups pg ON pg.id = pit.product_group_id
             WHERE pit.token = :token AND pit.is_active = true',
            [':token' => $token]
        );
    }

    /**
     * 使用邀请令牌
     */
    public static function useInvitationToken(int $tokenId): bool
    {
        $db = Database::getInstance();

        $db->query(
            'UPDATE product_invitation_tokens SET used_count = used_count + 1 WHERE id = :id',
            [':id' => $tokenId]
        );

        // 检查是否达到最大使用次数
        $token = $db->fetch(
            'SELECT max_uses, used_count FROM product_invitation_tokens WHERE id = :id',
            [':id' => $tokenId]
        );

        if ($token !== null && $token['max_uses'] > 0 && $token['used_count'] >= $token['max_uses']) {
            $db->update('product_invitation_tokens', ['is_active' => false], 'id = :id', [':id' => $tokenId]);
        }

        return true;
    }

    /**
     * 授予产品访问权限
     */
    public static function grantAccess(int $userId, int $productId, int $productGroupId, ?int $tokenId = null): bool
    {
        try {
            Database::getInstance()->insert('product_access_grants', [
                'user_id'             => $userId,
                'product_id'          => $productId,
                'product_group_id'    => $productGroupId,
                'granted_by_token_id' => $tokenId,
            ]);
            return true;
        } catch (\Throwable) {
            return false;
        }
    }
}
