"""
工单系统通知模块

支持邮件通知和站内通知（邮件通过 Celery 异步发送）
"""


def _get_system_config():
    """获取系统配置"""
    from apps.dashboard.models import SystemConfig
    try:
        return SystemConfig.get_config()
    except Exception:
        return None


def _get_site_url():
    """获取站点URL"""
    from django.conf import settings
    return getattr(settings, 'SITE_URL', 'http://localhost:8000')


def send_ticket_email(subject, template_name, context, recipient_list):
    """
    异步发送工单相关邮件（通过 Celery 任务）

    Args:
        subject: 邮件主题
        template_name: 邮件模板名称
        context: 模板上下文
        recipient_list: 收件人列表
    """
    if not recipient_list:
        return

    from apps.accounts.tasks import send_ticket_email_task
    send_ticket_email_task.delay(
        subject=subject,
        template_name=template_name,
        context=context,
        recipient_list=recipient_list,
    )


def notify_ticket_created(ticket):
    """
    通知工单创建
    - 通知管理员
    - 通知自动分配的处理人
    - 通知自动分配的处理组成员
    """
    context = {
        'ticket': ticket,
        'site_url': _get_site_url(),
    }

    recipients = []

    if ticket.assignee and ticket.assignee.email:
        recipients.append(ticket.assignee.email)

    if ticket.assigned_group:
        group_users = ticket.assigned_group.user_set.filter(
            is_active=True
        ).exclude(email='')
        for user in group_users:
            if user.email not in recipients:
                recipients.append(user.email)

    if recipients:
        send_ticket_email(
            subject=f'[2c2a] 新工单分配 - {ticket.ticket_no}',
            template_name='tickets/email/assigned.html',
            context=context,
            recipient_list=recipients
        )


def notify_ticket_assigned(ticket, old_assignee=None):
    """
    通知工单分配
    - 通知新的处理人
    - 通知处理组成员
    """
    context = {
        'ticket': ticket,
        'site_url': _get_site_url(),
        'old_assignee': old_assignee,
    }

    recipients = []

    if ticket.assignee and ticket.assignee.email:
        recipients.append(ticket.assignee.email)

    if ticket.assigned_group:
        group_users = ticket.assigned_group.user_set.filter(
            is_active=True
        ).exclude(email='')
        for user in group_users:
            if user.email not in recipients:
                recipients.append(user.email)

    if not recipients:
        return

    send_ticket_email(
        subject=f'[2c2a] 工单分配通知 - {ticket.ticket_no}',
        template_name='tickets/email/assigned.html',
        context=context,
        recipient_list=recipients
    )


def notify_ticket_status_changed(ticket, old_status, new_status):
    """
    通知工单状态变更
    - 通知创建者
    """
    if not ticket.creator or not ticket.creator.email:
        return

    # 如果创建者自己变更状态，不发送通知
    # 这里简化处理，实际应该传入操作人参数

    context = {
        'ticket': ticket,
        'site_url': _get_site_url(),
        'old_status': old_status,
        'new_status': new_status,
    }

    send_ticket_email(
        subject=f'[2c2a] 工单状态更新 - {ticket.ticket_no}',
        template_name='tickets/email/status_update.html',
        context=context,
        recipient_list=[ticket.creator.email]
    )


def notify_ticket_closed(ticket):
    """
    通知工单关闭
    - 通知创建者
    - 邀请评价
    """
    if not ticket.creator or not ticket.creator.email:
        return

    context = {
        'ticket': ticket,
        'site_url': _get_site_url(),
    }

    send_ticket_email(
        subject=f'[2c2a] 工单已关闭 - {ticket.ticket_no}',
        template_name='tickets/email/closed.html',
        context=context,
        recipient_list=[ticket.creator.email]
    )


def notify_new_comment(comment):
    """
    通知新评论
    - 通知工单相关人员
    """
    ticket = comment.ticket

    # 收集需要通知的用户
    recipients = []

    # 通知创建者（如果不是评论者自己）
    if ticket.creator and ticket.creator.email and ticket.creator != comment.author:
        recipients.append(ticket.creator.email)

    # 通知处理人（如果不是评论者自己）
    if ticket.assignee and ticket.assignee.email and ticket.assignee != comment.author:
        recipients.append(ticket.assignee.email)

    if not recipients:
        return

    context = {
        'ticket': ticket,
        'comment': comment,
        'site_url': _get_site_url(),
    }

    send_ticket_email(
        subject=f'[2c2a] 工单新评论 - {ticket.ticket_no}',
        template_name='tickets/email/new_comment.html',
        context=context,
        recipient_list=recipients
    )


def notify_overdue_ticket(ticket):
    """
    通知工单即将超时或已超时
    - 通知处理人
    - 通知处理组成员
    - 通知管理员
    """
    context = {
        'ticket': ticket,
        'site_url': _get_site_url(),
    }

    recipients = []

    if ticket.assignee and ticket.assignee.email:
        recipients.append(ticket.assignee.email)

    if ticket.assigned_group:
        group_users = ticket.assigned_group.user_set.filter(
            is_active=True
        ).exclude(email='')
        for user in group_users:
            if user.email not in recipients:
                recipients.append(user.email)

    if not recipients:
        return

    send_ticket_email(
        subject=f'[2c2a] 工单即将超时 - {ticket.ticket_no}',
        template_name='tickets/email/overdue.html',
        context=context,
        recipient_list=recipients
    )
