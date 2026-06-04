<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;
use App\Core\Cache;
use App\Service\CryptoService;
use App\Service\TaskQueue;

/**
 * 云桌面用户模型
 */
class CloudComputerUser
{
    /**
     * 根据 ID 查找云用户
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM cloud_computer_users WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 根据产品和用户名查找云用户
     */
    public static function findByProductAndUsername(int $productId, string $username): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM cloud_computer_users WHERE product_id = :product_id AND username = :username',
            [':product_id' => $productId, ':username' => $username]
        );
    }

    /**
     * 创建云用户
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $db->insert('cloud_computer_users', [
            'username'                => $data['username'],
            'fullname'                => $data['fullname'],
            'email'                   => $data['email'],
            'description'             => $data['description'] ?? '',
            'product_id'              => $data['product_id'],
            'status'                  => $data['status'] ?? 'active',
            'is_admin'                => $data['is_admin'] ?? false,
            'groups'                  => $data['groups'] ?? '',
            'disk_quota'              => $data['disk_quota'] ?? '{}',
            'created_from_request_id' => $data['created_from_request_id'] ?? null,
            'owner_id'                => $data['owner_id'] ?? null,
            'initial_password'        => $data['initial_password'] ?? '',
            'password_viewed'         => $data['password_viewed'] ?? false,
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('cloud_computer_users', 'id'))");

        return self::find((int) $id);
    }

    /**
     * 更新云用户
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'username', 'fullname', 'email', 'description', 'status',
            'is_admin', 'groups', 'disk_quota', 'owner_id',
            'initial_password', 'password_viewed', 'password_viewed_at',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('cloud_computer_users', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 获取用户的云用户列表（所有者或通过开通请求创建）
     */
    public static function getForUser(int $userId, ?int $siteGroupId = null): array
    {
        $sql = 'SELECT ccu.*, p.name AS product_name, p.display_name AS product_display_name,
                h.name AS host_name, h.hostname AS host_hostname
                FROM cloud_computer_users ccu
                INNER JOIN products p ON p.id = ccu.product_id
                INNER JOIN hosts h ON h.id = p.host_id
                WHERE ccu.owner_id = :user_id AND ccu.status != :deleted_status';

        $params = [':user_id' => $userId, ':deleted_status' => 'deleted'];

        if ($siteGroupId !== null) {
            $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        $sql .= ' ORDER BY ccu.created_at DESC';

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 获取所有云用户（带过滤条件）
     */
    public static function getAllWithFilters(array $filters = [], ?int $siteGroupId = null): array
    {
        $sql = 'SELECT ccu.*, p.name AS product_name, p.display_name AS product_display_name,
                h.name AS host_name, u.username AS owner_username
                FROM cloud_computer_users ccu
                INNER JOIN products p ON p.id = ccu.product_id
                INNER JOIN hosts h ON h.id = p.host_id
                LEFT JOIN users u ON u.id = ccu.owner_id
                WHERE 1=1';

        $params = [];

        if ($siteGroupId !== null) {
            $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        if (!empty($filters['status'])) {
            $sql .= ' AND ccu.status = :status';
            $params[':status'] = $filters['status'];
        }

        if (!empty($filters['product_id'])) {
            $sql .= ' AND ccu.product_id = :product_id';
            $params[':product_id'] = (int) $filters['product_id'];
        }

        if (!empty($filters['username'])) {
            $sql .= ' AND ccu.username ILIKE :username';
            $params[':username'] = '%' . $filters['username'] . '%';
        }

        if (!empty($filters['owner_id'])) {
            $sql .= ' AND ccu.owner_id = :owner_id';
            $params[':owner_id'] = (int) $filters['owner_id'];
        }

        $sql .= ' ORDER BY ccu.created_at DESC';

        $limit = (int) ($filters['limit'] ?? PAGE_SIZE);
        $offset = (int) ($filters['offset'] ?? 0);

        $sql .= " LIMIT {$limit} OFFSET {$offset}";

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 获取并销毁密码（一次性查看）
     */
    public static function getAndBurnPassword(int $id, int $userId): string
    {
        $cloudUser = self::find($id);

        if ($cloudUser === null) {
            return '';
        }

        // 验证权限
        if ((int) $cloudUser['owner_id'] !== $userId) {
            return '';
        }

        // 解密密码
        $crypto = new CryptoService();
        $password = $cloudUser['initial_password'];

        // 尝试解密，如果失败则返回原文（兼容未加密数据）
        $decrypted = $crypto->decrypt($password);
        if ($decrypted !== null) {
            $password = $decrypted;
        }

        // 标记为已查看
        self::update($id, [
            'password_viewed'    => true,
            'password_viewed_at' => date('c'),
        ]);

        return $password;
    }

    /**
     * 生成复杂密码
     */
    public static function generateComplexPassword(int $length = 16): string
    {
        $lowercase = 'abcdefghijkmnopqrstuvwxyz';
        $uppercase = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
        $numbers = '23456789';
        $special = '!@#$%^&*_-+=';

        $all = $lowercase . $uppercase . $numbers . $special;

        $password = '';
        // 确保每种类型至少一个
        $password .= $lowercase[random_int(0, strlen($lowercase) - 1)];
        $password .= $uppercase[random_int(0, strlen($uppercase) - 1)];
        $password .= $numbers[random_int(0, strlen($numbers) - 1)];
        $password .= $special[random_int(0, strlen($special) - 1)];

        for ($i = strlen($password); $i < $length; $i++) {
            $password .= $all[random_int(0, strlen($all) - 1)];
        }

        // 打乱顺序
        return str_shuffle($password);
    }

    /**
     * 派发远程操作到 Node.js Worker
     */
    public static function dispatchRemoteAction(int $userId, string $action): string
    {
        $taskQueue = new TaskQueue();
        return $taskQueue->dispatchCloudUserAction($userId, $action);
    }

    /**
     * 获取云用户的产品和主机信息
     */
    public static function getWithProductAndHost(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT ccu.*, p.name AS product_name, p.display_name AS product_display_name,
                    p.rdp_port AS product_rdp_port, p.display_hostname,
                    h.name AS host_name, h.hostname AS host_hostname,
                    h.rdp_port AS host_rdp_port, h.tunnel_token, h.tunnel_status
             FROM cloud_computer_users ccu
             INNER JOIN products p ON p.id = ccu.product_id
             INNER JOIN hosts h ON h.id = p.host_id
             WHERE ccu.id = :id',
            [':id' => $id]
        );
    }
}
