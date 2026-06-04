<?php

declare(strict_types=1);

namespace App\Service;

use App\Core\Database;
use App\Core\Cache;
use RuntimeException;

/**
 * WinRM 客户端服务 - PHP 端薄封装，将任务分派到 Node.js Worker
 *
 * PHP 不直接执行 WinRM 操作，而是通过任务队列将请求转发给 Node.js Worker 处理
 */
class WinrmService
{
    private Database $database;
    private Cache $cache;
    private TaskQueue $taskQueue;

    public function __construct(?Database $database = null, ?Cache $cache = null, ?TaskQueue $taskQueue = null)
    {
        $this->database = $database ?? Database::getInstance();
        $this->cache = $cache ?? Cache::getInstance();
        $this->taskQueue = $taskQueue ?? new TaskQueue($this->database, $this->cache);
    }

    /**
     * 分派 WinRM 任务到 Node.js Worker
     *
     * @param string $queue 队列名称 (hosts, operations, bootstrap, certificates, default)
     * @param string $taskType 任务类型
     * @param array $payload 任务数据
     * @return string 任务 ID
     */
    public function dispatchTask(string $queue, string $taskType, array $payload): string
    {
        return $this->taskQueue->push($queue, $taskType, $payload);
    }

    /**
     * 获取任务结果
     *
     * 优先从 Redis 获取，回退到数据库查询
     *
     * @param string $taskId 任务 ID
     * @return array|null 任务结果
     */
    public function getTaskResult(string $taskId): ?array
    {
        return $this->taskQueue->getResult($taskId);
    }

    /**
     * 获取任务进度
     *
     * @param string $taskId 任务 ID
     * @return array 进度信息
     */
    public function getTaskProgress(string $taskId): array
    {
        return $this->taskQueue->getProgress($taskId);
    }

    // ========================================================================
    // 便捷方法 - 常用 WinRM 操作
    // ========================================================================

    /**
     * 创建云电脑用户
     *
     * @param int $hostId 主机 ID
     * @param string $username 用户名
     * @param string $password 密码
     * @param string $description 描述
     * @return string 任务 ID
     */
    public function createUser(int $hostId, string $username, string $password, string $description = ''): string
    {
        return $this->dispatchTask('operations', 'create_user', [
            'host_id'     => $hostId,
            'username'    => $username,
            'password'    => $password,
            'description' => $description,
        ]);
    }

    /**
     * 删除云电脑用户
     *
     * @param int $hostId 主机 ID
     * @param string $username 用户名
     * @return string 任务 ID
     */
    public function deleteUser(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'delete_user', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 重置用户密码
     *
     * @param int $hostId 主机 ID
     * @param string $username 用户名
     * @param string $newPassword 新密码
     * @return string 任务 ID
     */
    public function resetPassword(int $hostId, string $username, string $newPassword): string
    {
        return $this->dispatchTask('operations', 'reset_password', [
            'host_id'      => $hostId,
            'username'     => $username,
            'new_password' => $newPassword,
        ]);
    }

    /**
     * 启用用户
     */
    public function enableUser(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'enable_user', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 禁用用户
     */
    public function disableUser(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'disable_user', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 提升用户为管理员
     */
    public function opUser(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'op_user', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 取消用户管理员
     */
    public function deopUser(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'deop_user', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 添加用户到远程桌面用户组
     */
    public function addToRemoteUsers(int $hostId, string $username): string
    {
        return $this->dispatchTask('operations', 'add_to_remote_users', [
            'host_id'  => $hostId,
            'username' => $username,
        ]);
    }

    /**
     * 执行远程命令
     */
    public function executeCommand(int $hostId, string $command): string
    {
        return $this->dispatchTask('operations', 'execute_command', [
            'host_id' => $hostId,
            'command' => $command,
        ]);
    }

    /**
     * 执行 PowerShell 脚本
     */
    public function executePowershell(int $hostId, string $script): string
    {
        return $this->dispatchTask('operations', 'execute_powershell', [
            'host_id' => $hostId,
            'script'  => $script,
        ]);
    }

    /**
     * 设置磁盘配额
     */
    public function setDiskQuota(int $hostId, string $username, array $quotaConfig): string
    {
        return $this->dispatchTask('operations', 'set_disk_quota', [
            'host_id'      => $hostId,
            'username'     => $username,
            'quota_config' => $quotaConfig,
        ]);
    }
}
