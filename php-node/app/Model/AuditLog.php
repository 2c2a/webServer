<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;

/**
 * 审计日志模型
 */
class AuditLog
{
    /**
     * 创建审计日志
     */
    public static function create(array $data): array
    {
        Database::getInstance()->insert('audit_logs', [
            'user_id'     => $data['user_id'] ?? null,
            'host_id'     => $data['host_id'] ?? null,
            'action'      => $data['action'],
            'details'     => json_encode($data['details'] ?? [], JSON_UNESCAPED_UNICODE),
            'ip_address'  => $data['ip_address'] ?? ($_SERVER['REMOTE_ADDR'] ?? null),
            'user_agent'  => $data['user_agent'] ?? ($_SERVER['HTTP_USER_AGENT'] ?? null),
            'success'     => $data['success'] ?? true,
        ]);

        $id = Database::getInstance()->fetchColumn("SELECT currval(pg_get_serial_sequence('audit_logs', 'id'))");

        return Database::getInstance()->fetch('SELECT * FROM audit_logs WHERE id = :id', [':id' => (int) $id]);
    }

    /**
     * 获取审计日志（带过滤）
     */
    public static function getWithFilters(array $filters = [], int $limit = 50): array
    {
        $sql = 'SELECT al.*, u.username
                FROM audit_logs al
                LEFT JOIN users u ON u.id = al.user_id
                WHERE 1=1';

        $params = [];

        if (!empty($filters['user_id'])) {
            $sql .= ' AND al.user_id = :user_id';
            $params[':user_id'] = (int) $filters['user_id'];
        }

        if (!empty($filters['host_id'])) {
            $sql .= ' AND al.host_id = :host_id';
            $params[':host_id'] = (int) $filters['host_id'];
        }

        if (!empty($filters['action'])) {
            $sql .= ' AND al.action = :action';
            $params[':action'] = $filters['action'];
        }

        if (isset($filters['success']) && $filters['success'] !== '') {
            $sql .= ' AND al.success = :success';
            $params[':success'] = (bool) $filters['success'];
        }

        if (!empty($filters['date_from'])) {
            $sql .= ' AND al.created_at >= :date_from';
            $params[':date_from'] = $filters['date_from'];
        }

        if (!empty($filters['date_to'])) {
            $sql .= ' AND al.created_at <= :date_to';
            $params[':date_to'] = $filters['date_to'];
        }

        if (!empty($filters['ip_address'])) {
            $sql .= ' AND al.ip_address = :ip_address';
            $params[':ip_address'] = $filters['ip_address'];
        }

        $sql .= ' ORDER BY al.created_at DESC';

        $offset = (int) ($filters['offset'] ?? 0);
        $sql .= " LIMIT {$limit} OFFSET {$offset}";

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 记录操作日志
     */
    public static function log(string $action, ?int $userId = null, ?int $hostId = null, array $details = [], bool $success = true): void
    {
        try {
            self::create([
                'action'     => $action,
                'user_id'    => $userId,
                'host_id'    => $hostId,
                'details'    => $details,
                'success'    => $success,
            ]);
        } catch (\Throwable) {
            // 审计日志写入失败不应影响主流程
        }
    }
}
