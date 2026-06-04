<?php

declare(strict_types=1);

namespace App\Service;

use App\Core\Cache;
use App\Core\Database;

/**
 * 任务队列服务 - 向 Node.js Worker 派发异步任务
 */
class TaskQueue
{
    private Cache $cache;
    private Database $database;

    /** 队列名称映射 */
    private const QUEUE_HOSTS = 'queue:hosts';
    private const QUEUE_OPERATIONS = 'queue:operations';
    private const QUEUE_BOOTSTRAP = 'queue:bootstrap';
    private const QUEUE_CERTIFICATES = 'queue:certificates';
    private const QUEUE_DEFAULT = 'queue:default';

    public function __construct()
    {
        $this->cache = Cache::getInstance();
        $this->database = Database::getInstance();
    }

    /**
     * 派发任务到队列
     *
     * @param string $taskType 任务类型
     * @param array $payload 任务载荷
     * string $queue 队列名称
     * int|null $createdBy 创建者 ID
     * string $name 任务名称
     * @return string 任务 ID
     */
    public function dispatch(string $taskType, array $payload, string $queue = self::QUEUE_DEFAULT, ?int $createdBy = null, string $name = ''): string
    {
        // 生成唯一任务 ID
        $taskId = $taskType . '-' . uniqid() . '-' . bin2hex(random_bytes(4));

        // 创建 async_tasks 记录
        $this->database->insert('async_tasks', [
            'task_id'       => $taskId,
            'name'          => $name ?: $taskType,
            'status'        => 'pending',
            'created_by_id' => $createdBy,
            'progress'      => 0,
        ]);

        // 推送到 Redis 队列
        $taskData = [
            'id'         => $taskId,
            'type'       => $taskType,
            'payload'    => $payload,
            'retryCount' => 0,
            'maxRetries' => 3,
            'createdAt'  => date('c'),
        ];

        $redis = $this->cache->getRedis();
        if ($redis !== null) {
            $redis->lpush($queue, json_encode($taskData, JSON_UNESCAPED_UNICODE));
        }

        return $taskId;
    }

    /**
     * 派发账号创建任务
     */
    public function dispatchAccountCreation(int $requestId, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'process_account_creation',
            ['requestId' => $requestId],
            self::QUEUE_OPERATIONS,
            $operatorId,
            "创建云桌面账号 (请求 #{$requestId})"
        );
    }

    /**
     * 派发主机连接测试任务
     */
    public function dispatchTestConnection(int $hostId, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'test_winrm_connection',
            ['hostId' => $hostId],
            self::QUEUE_HOSTS,
            $operatorId,
            "测试主机连接 (主机 #{$hostId})"
        );
    }

    /**
     * 派发云用户远程操作任务
     */
    public function dispatchCloudUserAction(int $userId, string $action, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'execute_cloud_user_remote_action',
            ['userId' => $userId, 'action' => $action],
            self::QUEUE_OPERATIONS,
            $operatorId,
            "云用户远程操作: {$action} (用户 #{$userId})"
        );
    }

    /**
     * 派发重置密码任务
     */
    public function dispatchResetPassword(int $cloudUserId, ?string $newPassword = null, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'remote_reset_password',
            ['cloudUserId' => $cloudUserId, 'newPassword' => $newPassword],
            self::QUEUE_OPERATIONS,
            $operatorId,
            "重置云用户密码 (用户 #{$cloudUserId})"
        );
    }

    /**
     * 派发磁盘配额设置任务
     */
    public function dispatchSetDiskQuota(int $cloudUserId, string $disk, int $quotaMb, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'remote_set_disk_quota',
            ['cloudUserId' => $cloudUserId, 'disk' => $disk, 'quotaMb' => $quotaMb],
            self::QUEUE_OPERATIONS,
            $operatorId,
            "设置磁盘配额 (用户 #{$cloudUserId})"
        );
    }

    /**
     * 派发获取磁盘信息任务
     */
    public function dispatchDiskInfo(int $hostId, ?int $operatorId = null): string
    {
        return $this->dispatch(
            'get_disk_info',
            ['hostId' => $hostId],
            self::QUEUE_HOSTS,
            $operatorId,
            "获取主机磁盘信息 (主机 #{$hostId})"
        );
    }

    /**
     * 获取任务状态
     */
    public function getTaskStatus(string $taskId): ?array
    {
        // 先从数据库获取
        $task = $this->database->fetch(
            'SELECT * FROM async_tasks WHERE task_id = :task_id',
            [':task_id' => $taskId]
        );

        if ($task === null) {
            return null;
        }

        $result = [
            'id'         => $task['id'],
            'task_id'    => $task['task_id'],
            'name'       => $task['name'],
            'status'     => $task['status'],
            'progress'   => (int) $task['progress'],
            'created_at' => $task['created_at'],
            'started_at' => $task['started_at'],
            'completed_at' => $task['completed_at'],
            'error_message' => $task['error_message'],
        ];

        // 尝试从 Redis 获取结果
        $redis = $this->cache->getRedis();
        if ($redis !== null) {
            $resultKey = 'task:result:' . $taskId;
            $resultData = $redis->get($resultKey);
            if ($resultData !== false) {
                $decoded = json_decode($resultData, true);
                if (is_array($decoded)) {
                    $result['result'] = $decoded['result'] ?? null;
                }
            }
        }

        return $result;
    }

    /**
     * 获取任务进度
     */
    public function getTaskProgress(string $taskId): array
    {
        $task = $this->database->fetch(
            'SELECT status, progress, error_message FROM async_tasks WHERE task_id = :task_id',
            [':task_id' => $taskId]
        );

        if ($task === null) {
            return ['status' => 'not_found', 'progress' => 0];
        }

        return [
            'status'   => $task['status'],
            'progress' => (int) $task['progress'],
            'error'    => $task['error_message'],
        ];
    }
}
