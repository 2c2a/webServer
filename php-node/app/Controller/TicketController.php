<?php

declare(strict_types=1);

namespace App\Controller;

use App\Core\Request;
use App\Core\Response;
use App\Core\Database;
use App\Core\Session;
use App\Core\Auth;
use App\Core\Cache;
use App\Core\Template;
use App\Core\Csrf;
use App\Core\Validator;
use App\Model\Ticket;
use App\Model\AuditLog;

/**
 * 工单控制器
 */
class TicketController
{
    public function __construct(
        private Request $request,
        private Response $response,
        private Database $database,
        private Session $session,
        private Auth $auth,
        private Cache $cache,
        private Template $template,
        private Csrf $csrf
    ) {}

    /**
     * 工单列表
     */
    public function list(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);

        $filters = [
            'status'   => $this->request->input('status', ''),
            'category' => $this->request->input('category', ''),
            'priority' => $this->request->input('priority', ''),
            'page'     => max(1, (int) $this->request->input('page', 1)),
        ];

        $filters['offset'] = ($filters['page'] - 1) * PAGE_SIZE;

        $tickets = Ticket::getWithFilters((int) $user['id'], $isStaff, $filters);
        $categories = Ticket::getCategories();

        $html = $this->template->render('tickets/list', [
            'user'       => $user,
            'tickets'    => $tickets,
            'categories' => $categories,
            'filters'    => $filters,
            'isStaff'    => $isStaff,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 创建工单表单
     */
    public function create(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $categories = Ticket::getCategories();

        $html = $this->template->render('tickets/create', [
            'user'       => $user,
            'categories' => $categories,
            'csrfToken'  => $this->csrf->token(),
            'error'      => $this->session->flash('error'),
        ]);

        return $this->response->html($html);
    }

    /**
     * 保存工单
     */
    public function createPost(): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $subject = trim($this->request->input('subject', ''));
        $description = trim($this->request->input('description', ''));
        $category = $this->request->input('category', 'other');
        $priority = $this->request->input('priority', 'medium');

        // 验证输入
        $validator = new Validator($this->request->all());
        $validator->rule('required', ['subject', 'description']);

        if (!$validator->validate()) {
            $this->session->flash('error', '请填写标题和描述');
            $this->session->flash('old_input', compact('subject', 'description', 'category', 'priority'));
            return redirect('/tickets/create');
        }

        if (mb_strlen($subject) > 200) {
            $this->session->flash('error', '标题不能超过 200 个字符');
            return redirect('/tickets/create');
        }

        // 创建工单
        $ticket = Ticket::create([
            'subject'    => $subject,
            'description' => $description,
            'category'   => $category,
            'priority'   => $priority,
            'created_by' => (int) $user['id'],
        ]);

        AuditLog::log('ticket_created', (int) $user['id'], null, [
            'ticket_id'  => (int) $ticket['id'],
            'ticket_no'  => $ticket['ticket_no'],
            'subject'    => $subject,
        ]);

        $this->session->flash('success', '工单已创建');
        return redirect('/tickets/' . $ticket['id']);
    }

    /**
     * 工单详情
     */
    public function detail(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return redirect('/login');
        }

        $ticket = Ticket::find($id);

        if ($ticket === null) {
            $this->session->flash('error', '工单不存在');
            return redirect('/tickets');
        }

        // 权限检查
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser && (int) $ticket['created_by'] !== (int) $user['id']) {
            $this->session->flash('error', '权限不足');
            return redirect('/tickets');
        }

        // 获取评论和活动
        $comments = Ticket::getComments($id);
        $activities = Ticket::getActivities($id);
        $categories = Ticket::getCategories();

        $html = $this->template->render('tickets/detail', [
            'user'       => $user,
            'ticket'     => $ticket,
            'comments'   => $comments,
            'activities' => $activities,
            'categories' => $categories,
            'isStaff'    => $isStaff,
            'isSuperuser' => $isSuperuser,
            'csrfToken'  => $this->csrf->token(),
        ]);

        return $this->response->html($html);
    }

    /**
     * 添加评论
     */
    public function addComment(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $ticket = Ticket::find($id);

        if ($ticket === null) {
            return $this->response->json(['success' => false, 'message' => '工单不存在'], 404);
        }

        // 权限检查
        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        if (!$isStaff && !$isSuperuser && (int) $ticket['created_by'] !== (int) $user['id']) {
            return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
        }

        $content = trim($this->request->input('content', ''));
        $isInternal = (bool) $this->request->input('is_internal', false);

        if (empty($content)) {
            return $this->response->json(['success' => false, 'message' => '评论内容不能为空'], 400);
        }

        // 只有员工可以添加内部评论
        if ($isInternal && !$isStaff && !$isSuperuser) {
            $isInternal = false;
        }

        $comment = Ticket::addComment($id, (int) $user['id'], $content, $isInternal);

        AuditLog::log('ticket_comment_added', (int) $user['id'], null, [
            'ticket_id'   => $id,
            'comment_id'  => (int) $comment['id'],
            'is_internal' => $isInternal,
        ]);

        return $this->response->json([
            'success' => true,
            'message' => '评论已添加',
            'comment' => $comment,
        ]);
    }

    /**
     * 更新工单状态
     */
    public function updateStatus(int $id): Response
    {
        $user = $this->auth->user();

        if ($user === null) {
            return $this->response->json(['success' => false, 'message' => '未登录'], 401);
        }

        $ticket = Ticket::find($id);

        if ($ticket === null) {
            return $this->response->json(['success' => false, 'message' => '工单不存在'], 404);
        }

        $newStatus = $this->request->input('status', '');
        $resolution = trim($this->request->input('resolution', ''));

        $validStatuses = ['open', 'in_progress', 'resolved', 'closed'];

        if (!in_array($newStatus, $validStatuses, true)) {
            return $this->response->json(['success' => false, 'message' => '无效的状态'], 400);
        }

        $isStaff = (bool) ($user['is_staff'] ?? false);
        $isSuperuser = (bool) ($user['is_superuser'] ?? false);

        // 权限检查：普通用户只能关闭自己的工单
        if (!$isStaff && !$isSuperuser) {
            if ((int) $ticket['created_by'] !== (int) $user['id']) {
                return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
            }

            // 普通用户只能关闭或重新打开
            if (!in_array($newStatus, ['closed', 'open'], true)) {
                return $this->response->json(['success' => false, 'message' => '权限不足'], 403);
            }
        }

        $updateData = ['status' => $newStatus];

        if ($newStatus === 'resolved' || $newStatus === 'closed') {
            if (!empty($resolution)) {
                $updateData['resolution'] = $resolution;
            }
        }

        Ticket::update($id, $updateData);

        // 记录活动
        $statusLabels = [
            'open' => '待处理',
            'in_progress' => '处理中',
            'resolved' => '已解决',
            'closed' => '已关闭',
        ];

        Database::getInstance()->insert('ticket_activities', [
            'ticket_id'   => $id,
            'actor_id'    => (int) $user['id'],
            'action'      => 'status_changed',
            'description' => '状态变更为: ' . ($statusLabels[$newStatus] ?? $newStatus),
        ]);

        AuditLog::log('ticket_status_updated', (int) $user['id'], null, [
            'ticket_id'  => $id,
            'old_status' => $ticket['status'],
            'new_status' => $newStatus,
        ]);

        return $this->response->json([
            'success' => true,
            'message' => '状态已更新',
        ]);
    }
}
