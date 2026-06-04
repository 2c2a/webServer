<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;

/**
 * 工单模型
 */
class Ticket
{
    /**
     * 根据 ID 查找工单
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM tickets WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 根据工单号查找工单
     */
    public static function findByTicketNo(string $ticketNo): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM tickets WHERE ticket_no = :ticket_no',
            [':ticket_no' => $ticketNo]
        );
    }

    /**
     * 创建工单
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $ticketNo = $data['ticket_no'] ?? self::generateTicketNo();

        $db->insert('tickets', [
            'ticket_no'   => $ticketNo,
            'subject'     => $data['subject'],
            'description' => $data['description'],
            'category'    => $data['category'] ?? 'other',
            'priority'    => $data['priority'] ?? 'medium',
            'status'      => $data['status'] ?? 'open',
            'created_by'  => $data['created_by'],
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('tickets', 'id'))");

        // 记录活动
        self::addActivity((int) $id, (int) $data['created_by'], 'created', '工单已创建');

        return self::find((int) $id);
    }

    /**
     * 更新工单
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'subject', 'description', 'category', 'priority', 'status',
            'assigned_to', 'resolution',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('tickets', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 获取工单列表（带过滤和权限控制）
     */
    public static function getWithFilters(int $userId, bool $isStaff, array $filters = []): array
    {
        $sql = 'SELECT t.*, u.username AS creator_username
                FROM tickets t
                INNER JOIN users u ON u.id = t.created_by
                WHERE 1=1';

        $params = [];

        // 非员工只能看自己的工单
        if (!$isStaff) {
            $sql .= ' AND t.created_by = :user_id';
            $params[':user_id'] = $userId;
        }

        // 状态过滤
        if (!empty($filters['status'])) {
            $sql .= ' AND t.status = :status';
            $params[':status'] = $filters['status'];
        }

        // 分类过滤
        if (!empty($filters['category'])) {
            $sql .= ' AND t.category = :category';
            $params[':category'] = $filters['category'];
        }

        // 优先级过滤
        if (!empty($filters['priority'])) {
            $sql .= ' AND t.priority = :priority';
            $params[':priority'] = $filters['priority'];
        }

        $sql .= ' ORDER BY t.created_at DESC';

        $limit = (int) ($filters['limit'] ?? PAGE_SIZE);
        $offset = (int) ($filters['offset'] ?? 0);

        $sql .= " LIMIT {$limit} OFFSET {$offset}";

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 添加评论
     */
    public static function addComment(int $ticketId, int $authorId, string $content, bool $isInternal = false): array
    {
        $db = Database::getInstance();

        $db->insert('ticket_comments', [
            'ticket_id'   => $ticketId,
            'author_id'   => $authorId,
            'content'     => $content,
            'is_internal' => $isInternal,
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('ticket_comments', 'id'))");

        // 记录活动
        $action = $isInternal ? 'internal_comment' : 'comment';
        self::addActivity($ticketId, $authorId, $action, '添加了' . ($isInternal ? '内部' : '') . '评论');

        return $db->fetch('SELECT * FROM ticket_comments WHERE id = :id', [':id' => (int) $id]);
    }

    /**
     * 获取工单评论
     */
    public static function getComments(int $ticketId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT tc.*, u.username AS author_username, u.avatar AS author_avatar
             FROM ticket_comments tc
             INNER JOIN users u ON u.id = tc.author_id
             WHERE tc.ticket_id = :ticket_id
             ORDER BY tc.created_at ASC',
            [':ticket_id' => $ticketId]
        );
    }

    /**
     * 获取工单活动记录
     */
    public static function getActivities(int $ticketId): array
    {
        return Database::getInstance()->fetchAll(
            'SELECT ta.*, u.username AS actor_username
             FROM ticket_activities ta
             LEFT JOIN users u ON u.id = ta.actor_id
             WHERE ta.ticket_id = :ticket_id
             ORDER BY ta.created_at ASC',
            [':ticket_id' => $ticketId]
        );
    }

    /**
     * 生成工单号
     */
    public static function generateTicketNo(): string
    {
        $prefix = 'TK';
        $date = date('Ymd');
        $random = strtoupper(bin2hex(random_bytes(3)));

        return $prefix . $date . $random;
    }

    /**
     * 获取工单分类列表
     */
    public static function getCategories(): array
    {
        return [
            ['value' => 'account', 'label' => '账号问题'],
            ['value' => 'connection', 'label' => '连接问题'],
            ['value' => 'performance', 'label' => '性能问题'],
            ['value' => 'data', 'label' => '数据问题'],
            ['value' => 'access', 'label' => '权限问题'],
            ['value' => 'other', 'label' => '其他'],
        ];
    }

    /**
     * 记录工单活动
     */
    private static function addActivity(int $ticketId, int $actorId, string $action, string $description): void
    {
        Database::getInstance()->insert('ticket_activities', [
            'ticket_id'   => $ticketId,
            'actor_id'    => $actorId,
            'action'      => $action,
            'description' => $description,
        ]);
    }
}
