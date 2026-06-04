<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;
use App\Service\TaskQueue;

/**
 * 主机模型
 */
class Host
{
    /**
     * 根据 ID 查找主机
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM hosts WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 获取所有主机
     */
    public static function all(): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT * FROM hosts ORDER BY name'
        );
    }

    /**
     * 创建主机
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $db->insert('hosts', [
            'name'            => $data['name'],
            'os_type'         => $data['os_type'] ?? 'windows',
            'hostname'        => $data['hostname'],
            'connection_type' => $data['connection_type'] ?? 'winrm',
            'auth_method'     => $data['auth_method'] ?? 'ntlm',
            'port'            => $data['port'] ?? 5985,
            'rdp_port'        => $data['rdp_port'] ?? 3389,
            'use_ssl'         => $data['use_ssl'] ?? false,
            'username'        => $data['username'] ?? '',
            'password'        => $data['password'],
            'description'     => $data['description'] ?? '',
            'created_by_id'   => $data['created_by_id'] ?? null,
            'site_group_id'   => $data['site_group_id'] ?? null,
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('hosts', 'id'))");

        return self::find((int) $id);
    }

    /**
     * 更新主机
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'name', 'os_type', 'hostname', 'connection_type', 'auth_method',
            'port', 'rdp_port', 'use_ssl', 'username', 'password',
            'cert_pem_path', 'cert_key_path', 'os_version', 'status',
            'description', 'site_group_id', 'ntlm_fallback_user', 'ntlm_fallback_password',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('hosts', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 删除主机
     */
    public static function delete(int $id): bool
    {
        $rows = Database::getInstance()->delete('hosts', 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 根据站点组获取主机
     */
    public static function getBySiteGroup(?int $siteGroupId): array
    {
        if ($siteGroupId === null) {
            return Database::getInstance()->fetchAll(
                'SELECT * FROM hosts WHERE site_group_id IS NULL ORDER BY name'
            );
        }

        return Database::getInstance()->fetchAll(
            'SELECT * FROM hosts WHERE site_group_id = :sg_id ORDER BY name',
            [':sg_id' => $siteGroupId]
        );
    }

    /**
     * 获取供应商关联的主机
     */
    public static function getForProvider(int $userId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT h.* FROM hosts h
             INNER JOIN host_providers hp ON hp.host_id = h.id
             WHERE hp.user_id = :user_id
             ORDER BY h.name',
            [':user_id' => $userId]
        );
    }

    /**
     * 更新隧道状态
     */
    public static function updateTunnelStatus(int $id, string $status, array $data = []): bool
    {
        $updateData = array_merge(['tunnel_status' => $status], $data);

        if ($status === 'connected') {
            $updateData['tunnel_connected_at'] = date('c');
            $updateData['tunnel_last_seen_at'] = date('c');
            $updateData['status'] = 'online';
        } elseif ($status === 'disconnected' || $status === 'no_tunnel') {
            $updateData['status'] = 'offline';
        }

        return self::update($id, $updateData);
    }

    /**
     * 更新证书配置状态
     */
    public static function updateCertStatus(int $id, string $status): bool
    {
        $updateData = ['cert_provision_status' => $status];

        if ($status === 'configured') {
            $updateData['cert_activated_at'] = date('c');
        }

        return self::update($id, $updateData);
    }

    /**
     * 派发连接测试任务到 Node.js Worker
     */
    public static function dispatchTestConnection(int $id, ?int $operatorId = null): string
    {
        $taskQueue = new TaskQueue();
        return $taskQueue->dispatchTestConnection($id, $operatorId);
    }

    /**
     * 获取主机的管理员列表
     */
    public static function getAdministrators(int $hostId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT u.* FROM users u
             INNER JOIN host_administrators ha ON ha.user_id = u.id
             WHERE ha.host_id = :host_id',
            [':host_id' => $hostId]
        );
    }

    /**
     * 获取主机的供应商列表
     */
    public static function getProviders(int $hostId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT u.* FROM users u
             INNER JOIN host_providers hp ON hp.user_id = u.id
             WHERE hp.host_id = :host_id',
            [':host_id' => $hostId]
        );
    }
}
