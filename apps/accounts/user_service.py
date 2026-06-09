"""
用户服务模块

集中处理用户迁移、封禁同步、账户合并、邮箱绑定等核心业务逻辑。
"""

import logging

from django.db import transaction
from django.contrib.auth import get_user_model

from .models import UserEmail, UserBan, UserBanHistory

User = get_user_model()
logger = logging.getLogger(__name__)


# ── 用户迁移 ──────────────────────────────────────────


def check_user_migration(user, site_group):
    """
    检查用户是否需要迁移到指定站点组。

    Returns:
        dict: {
            'needs_migration': bool,
            'already_member': bool,
            'user_banned': bool,
        }
    """
    if site_group is None:
        return {"needs_migration": False, "already_member": True, "user_banned": False}

    # 超级管理员不需要迁移，相当于所有站点的管理员
    if user.is_superuser:
        return {"needs_migration": False, "already_member": True, "user_banned": False}

    is_member = user.site_groups.filter(pk=site_group.pk).exists()
    if is_member:
        return {"needs_migration": False, "already_member": True, "user_banned": False}

    if UserBan.objects.filter(user=user).exists():
        return {"needs_migration": False, "already_member": False, "user_banned": True}

    return {"needs_migration": True, "already_member": False, "user_banned": False}


def migrate_user_to_site_group(user, site_group):
    """
    将用户迁移到指定站点组。

    仅添加 site_groups 关联，不改变用户数据。
    迁移前需检查邮箱后缀合规性。

    Returns:
        dict: {'success': bool, 'reason': str}
    """
    if site_group is None:
        return {"success": False, "reason": "无效的站点组"}

    if UserBan.objects.filter(user=user).exists():
        return {"success": False, "reason": "用户已被封禁，无法迁移"}

    if user.site_groups.filter(pk=site_group.pk).exists():
        return {"success": False, "reason": "用户已在该站点组中"}

    # 检查邮箱后缀合规性
    from utils.site_group import get_effective_config

    ec = get_effective_config(site_group)
    suffix_data = ec.get_email_suffix_lists()
    has_whitelist = bool(suffix_data["whitelist"])
    has_blacklist = bool(suffix_data["blacklist"])

    if has_whitelist or has_blacklist:
        # 站点组配置了邮箱后缀限制，需要检查合规性
        user_emails = UserEmail.objects.filter(user=user)
        email_list = list(user_emails.values_list("email", flat=True))
        # 兼容旧用户：如果没有 UserEmail 记录，回退到 User.email
        if not email_list and user.email:
            email_list = [user.email]

        has_compliant_email = any(ec.is_email_suffix_allowed(e) for e in email_list)

        if not has_compliant_email:
            return {
                "success": False,
                "reason": "email_not_compliant",
                "message": "您的邮箱不满足该站点的邮箱后缀要求，请先绑定符合条件的邮箱",
            }

    user.site_groups.add(site_group)
    logger.info(
        f"用户 {user.username}(id={user.pk}) 已迁移到站点组 "
        f"{site_group.name}(id={site_group.pk})"
    )
    return {"success": True, "reason": "迁移成功"}


# ── 封禁同步 ──────────────────────────────────────────


def ban_user(user, reason="", banned_by=None):
    """
    全局封禁用户。

    使用自定义 UserBan 模型替代 Django 的 is_active 字段。
    封禁是全局的，影响用户在所有站点组的访问。
    封禁污染通过 bind_email 触发：当用户绑定被封禁用户的邮箱时，
    当前用户也会被封禁。
    """
    ban, created = UserBan.objects.get_or_create(
        user=user,
        defaults={"reason": reason, "banned_by": banned_by},
    )
    if not created:
        # 已有封禁记录，更新理由
        if reason:
            ban.reason = reason
        if banned_by:
            ban.banned_by = banned_by
        ban.save()

    if created:
        logger.info(
            f"用户 {user.username}(id={user.pk}) 已被封禁。"
            f"原因: {reason}，操作者: {banned_by}"
        )
    return ban


def unban_user(user, unbanned_by=None):
    """
    解封用户。

    将活跃封禁记录归档到 UserBanHistory，然后删除。
    """
    ban = UserBan.objects.filter(user=user).first()
    if not ban:
        return

    # 归档到历史记录
    UserBanHistory.objects.create(
        user=user,
        reason=ban.reason,
        banned_by=ban.banned_by,
        unbanned_by=unbanned_by,
        banned_at=ban.created_at,
    )
    ban.delete()
    logger.info(
        f"用户 {user.username}(id={user.pk}) 已解封。操作者: {unbanned_by}"
    )


def check_ban_status(email):
    """
    检查邮箱关联的账户是否被封禁。

    用于注册/忘记密码时检查，防止通过被封禁邮箱绕过。

    Returns:
        dict: {'is_banned': bool, 'user': User or None}
    """
    # 先检查 UserEmail 表
    user_email = UserEmail.objects.filter(email=email).first()
    if user_email and UserBan.objects.filter(user=user_email.user).exists():
        return {"is_banned": True, "user": user_email.user}

    # 再检查 User.email 字段（兼容旧数据）
    user = User.objects.filter(email=email).first()
    if user and UserBan.objects.filter(user=user).exists():
        return {"is_banned": True, "user": user}

    return {"is_banned": False, "user": user}


# ── 账户合并 ──────────────────────────────────────────


def merge_accounts(source_user, target_user, keep_newer=True):
    """
    合并两个账户。

    将 source_user 的数据迁移到 target_user，然后删除 source_user。
    默认保留较新的账户（keep_newer=True），用户可选保留较旧的。

    Args:
        source_user: 被合并的账户（将被删除）
        target_user: 保留的账户
        keep_newer: True=新到旧(source=旧,target=新), False=旧到新(source=新,target=旧)

    Returns:
        dict: {'success': bool, 'reason': str}
    """
    if source_user.pk == target_user.pk:
        return {"success": False, "reason": "不能合并同一账户"}

    if not keep_newer:
        # 旧到新：source 是较新的，target 是较旧的
        source_user, target_user = target_user, source_user

    with transaction.atomic():
        # 迁移 site_groups
        for sg in source_user.site_groups.all():
            target_user.site_groups.add(sg)

        # 迁移 UserEmail
        UserEmail.objects.filter(user=source_user).exclude(
            email__in=UserEmail.objects.filter(user=target_user).values_list(
                "email", flat=True
            )
        ).update(user=target_user)

        # 迁移 groups
        for group in source_user.groups.all():
            target_user.groups.add(group)

        # 迁移 UserProfile（如果 target 没有）
        if not hasattr(target_user, "profile") and hasattr(source_user, "profile"):
            source_user.profile.user = target_user
            source_user.profile.save()

        # 如果 source 的主邮箱不在 target 的邮箱列表中，添加为子邮箱
        source_primary = UserEmail.objects.filter(
            user=source_user, is_primary=True
        ).first()
        if source_primary:
            if not UserEmail.objects.filter(
                user=target_user, email=source_primary.email
            ).exists():
                source_primary.user = target_user
                source_primary.is_primary = False
                source_primary.save()

        # 如果 target 没有任何邮箱，把 source 的邮箱都迁移过来
        if not UserEmail.objects.filter(user=target_user).exists():
            UserEmail.objects.filter(user=source_user).update(user=target_user)

        # 同步封禁状态
        source_banned = UserBan.objects.filter(user=source_user).first()
        if source_banned and not UserBan.objects.filter(user=target_user).exists():
            UserBan.objects.create(
                user=target_user,
                reason=source_banned.reason,
                banned_by=source_banned.banned_by,
            )

        # 删除被合并的账户
        source_user.delete()

        logger.info(
            f"账户合并: 用户 {source_user.username}(id={source_user.pk}) "
            f"已合并到 {target_user.username}(id={target_user.pk})"
        )

    return {"success": True, "reason": "合并成功", "kept_user": target_user}


# ── 邮箱绑定 ──────────────────────────────────────────


def bind_email(user, email, is_primary=False):
    """
    绑定邮箱到用户账户。

    如果该邮箱已被其他账户使用：
    - 如果那个账户被封禁，同步封禁到当前用户（封禁污染）
    - 如果那个账户正常，触发账户合并

    Args:
        user: 当前用户
        email: 要绑定的邮箱
        is_primary: 是否设为主邮箱

    Returns:
        dict: {
            'success': bool,
            'action': 'bound'|'banned'|'merge_required',
            'reason': str,
            'merge_info': dict or None,
        }
    """
    # 检查邮箱是否已被绑定
    existing = UserEmail.objects.filter(email=email).first()
    if existing:
        if existing.user.pk == user.pk:
            return {
                "success": False,
                "action": "bound",
                "reason": "该邮箱已绑定到当前账户",
                "merge_info": None,
            }

        other_user = existing.user

        # 封禁污染：如果邮箱关联的账户被封禁，同步封禁当前用户
        if UserBan.objects.filter(user=other_user).exists():
            ban_user(
                user, reason=f"绑定了被封禁账户 {other_user.username} 的邮箱 {email}"
            )
            return {
                "success": False,
                "action": "banned",
                "reason": f"该邮箱关联的账户已被封禁，您的账户也已被同步封禁",
                "merge_info": None,
            }

        # 账户合并：需要用户确认
        return {
            "success": False,
            "action": "merge_required",
            "reason": f"该邮箱已被账户 {other_user.username} 使用，需要进行账户合并",
            "merge_info": {
                "other_user_id": other_user.pk,
                "other_username": other_user.username,
                "other_created_at": str(other_user.created_at),
                "current_user_id": user.pk,
                "current_username": user.username,
                "current_created_at": str(user.created_at),
            },
        }

    # 正常绑定
    UserEmail.objects.create(
        user=user,
        email=email,
        is_primary=is_primary,
        is_verified=False,
    )

    # 如果设为主邮箱，同步更新 User.email
    if is_primary:
        user.email = email
        user.save(update_fields=["email"])

    return {
        "success": True,
        "action": "bound",
        "reason": "邮箱绑定成功",
        "merge_info": None,
    }


def set_primary_email(user, email):
    """设置主邮箱"""
    ue = UserEmail.objects.filter(user=user, email=email).first()
    if not ue:
        return {"success": False, "reason": "该邮箱未绑定到当前账户"}

    ue.is_primary = True
    ue.save()

    user.email = email
    user.save(update_fields=["email"])

    return {"success": True, "reason": "主邮箱设置成功"}


def unbind_email(user, email):
    """解绑邮箱（不能解绑主邮箱）"""
    ue = UserEmail.objects.filter(user=user, email=email).first()
    if not ue:
        return {"success": False, "reason": "该邮箱未绑定到当前账户"}

    if ue.is_primary:
        return {"success": False, "reason": "不能解绑主邮箱，请先设置其他邮箱为主邮箱"}

    ue.delete()
    return {"success": True, "reason": "邮箱解绑成功"}
