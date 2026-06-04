<?php

declare(strict_types=1);

namespace App\Model;

use App\Core\Database;
use App\Service\TaskQueue;

/**
 * 开通请求模型
 */
class AccountOpeningRequest
{
    /**
     * 根据 ID 查找请求
     */
    public static function find(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT * FROM account_opening_requests WHERE id = :id',
            [':id' => $id]
        );
    }

    /**
     * 创建开通请求
     */
    public static function create(array $data): array
    {
        $db = Database::getInstance();

        $db->insert('account_opening_requests', [
            'applicant_id'          => $data['applicant_id'],
            'contact_email'         => $data['contact_email'],
            'contact_phone'         => $data['contact_phone'] ?? null,
            'username'              => $data['username'],
            'user_fullname'         => $data['user_fullname'],
            'user_email'            => $data['user_email'],
            'user_description'      => $data['user_description'] ?? '',
            'target_product_id'     => $data['target_product_id'],
            'requested_disk_capacity' => $data['requested_disk_capacity'] ?? '{}',
            'status'                => $data['status'] ?? 'pending',
        ]);

        $id = $db->fetchColumn("SELECT currval(pg_get_serial_sequence('account_opening_requests', 'id'))");

        return self::find((int) $id);
    }

    /**
     * 更新开通请求
     */
    public static function update(int $id, array $data): bool
    {
        $allowed = [
            'contact_email', 'contact_phone', 'username', 'user_fullname',
            'user_email', 'user_description', 'target_product_id',
            'requested_disk_capacity', 'status', 'approved_by_id',
            'approval_date', 'approval_notes', 'cloud_user_id',
            'cloud_user_password', 'result_message', 'retry_count',
        ];

        $updateData = array_intersect_key($data, array_flip($allowed));

        if (empty($updateData)) {
            return false;
        }

        $rows = Database::getInstance()->update('account_opening_requests', $updateData, 'id = :id', [':id' => $id]);

        return $rows > 0;
    }

    /**
     * 获取开通请求列表（带过滤和权限控制）
     */
    public static function getWithFilters(int $userId, bool $isStaff, bool $isSuperuser, array $filters = [], ?int $siteGroupId = null): array
    {
        $sql = 'SELECT aor.*, p.name AS product_name, p.display_name AS product_display_name,
                u.username AS applicant_username, u.email AS applicant_email,
                ab.username AS approver_username
                FROM account_opening_requests aor
                INNER JOIN products p ON p.id = aor.target_product_id
                INNER JOIN users u ON u.id = aor.applicant_id
                LEFT JOIN users ab ON ab.id = aor.approved_by_id
                WHERE 1=1';

        $params = [];

        // 非管理员只能看自己的请求
        if (!$isStaff && !$isSuperuser) {
            $sql .= ' AND aor.applicant_id = :user_id';
            $params[':user_id'] = $userId;
        }

        // 站点组过滤
        if ($siteGroupId !== null && ($isStaff || $isSuperuser)) {
            $sql .= ' AND (p.site_group_id = :sg_id OR p.site_group_id IS NULL)';
            $params[':sg_id'] = $siteGroupId;
        }

        // 状态过滤
        if (!empty($filters['status'])) {
            $sql .= ' AND aor.status = :status';
            $params[':status'] = $filters['status'];
        }

        // 产品过滤
        if (!empty($filters['product_id'])) {
            $sql .= ' AND aor.target_product_id = :product_id';
            $params[':product_id'] = (int) $filters['product_id'];
        }

        $sql .= ' ORDER BY aor.created_at DESC';

        $limit = (int) ($filters['limit'] ?? PAGE_SIZE);
        $offset = (int) ($filters['offset'] ?? 0);

        $sql .= " LIMIT {$limit} OFFSET {$offset}";

        return Database::getInstance()->fetchAll($sql, $params);
    }

    /**
     * 审批通过请求
     */
    public static function approve(int $id, int $approverId, string $notes = ''): bool
    {
        $request = self::find($id);

        if ($request === null || $request['status'] !== 'pending') {
            return false;
        }

        return self::update($id, [
            'status'         => 'approved',
            'approved_by_id' => $approverId,
            'approval_date'  => date('c'),
            'approval_notes' => $notes,
        ]);
    }

    /**
     * 拒绝请求
     */
    public static function reject(int $id, int $approverId, string $notes = ''): bool
    {
        $request = self::find($id);

        if ($request === null || $request['status'] !== 'pending') {
            return false;
        }

        return self::update($id, [
            'status'         => 'rejected',
            'approved_by_id' => $approverId,
            'approval_date'  => date('c'),
            'approval_notes' => $notes,
        ]);
    }

    /**
     * 重试失败的请求
     */
    public static function retry(int $id, ?int $operatorId = null): bool
    {
        $request = self::find($id);

        if ($request === null || $request['status'] !== 'failed') {
            return false;
        }

        // 更新状态为已审批，准备重新创建
        self::update($id, [
            'status'         => 'approved',
            'retry_count'    => ($request['retry_count'] ?? 0) + 1,
            'result_message' => '等待重试...',
        ]);

        // 派发创建任务
        self::dispatchCreationTask($id);

        return true;
    }

    /**
     * 派发账号创建任务
     */
    public static function dispatchCreationTask(int $requestId): string
    {
        $taskQueue = new TaskQueue();
        return $taskQueue->dispatchAccountCreation($requestId);
    }

    /**
     * 获取请求详情（含产品和申请人信息）
     */
    public static function findWithDetails(int $id): ?array
    {
        return Database::getInstance()->fetch(
            'SELECT aor.*, p.name AS product_name, p.display_name AS product_display_name,
                    p.auto_approval, p.visibility, p.limit_one_per_user,
                    h.name AS host_name, h.status AS host_status,
                    u.username AS applicant_username, u.email AS applicant_email,
                    ab.username AS approver_username
             FROM account_opening_requests aor
             INNER JOIN products p ON p.id = aor.target_product_id
             INNER JOIN hosts h ON h.id = p.host_id
             INNER JOIN users u ON u.id = aor.applicant_id
             LEFT JOIN users ab ON ab.id = aor.approved_by_id
             WHERE aor.id = :id',
            [':id' => $id]
        );
    }
}
