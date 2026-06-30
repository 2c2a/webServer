"""审计日志服务：提供带租户隔离的审计日志创建辅助函数。

使用 create_audit_log() 创建审计记录时自动注入 site_group_id，
确保审计日志与操作发生的租户上下文一致。
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.tenant.resolver import TenantContext


async def create_audit_log(
    db: AsyncSession,
    action: str,
    *,
    user_id: int | None = None,
    tenant: TenantContext | None = None,
    host_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    success: bool = True,
    details: dict | None = None,
    result: str | None = None,
    content_type: str | None = None,
    object_id: int | None = None,
    commit: bool = True,
) -> AuditLog:
    """创建审计日志记录（自动注入租户上下文）。

    Args:
        db: 异步数据库会话
        action: 操作类型（如 "host.create", "user.login"）
        user_id: 操作用户 ID
        tenant: 租户上下文，用于自动填充 site_group_id
        host_id: 关联主机 ID
        ip_address: 客户端 IP
        user_agent: User-Agent
        success: 操作是否成功
        details: 操作详情（JSON）
        result: 操作结果描述
        content_type: 关联对象类型
        object_id: 关联对象 ID
        commit: 是否立即提交（False 时由调用方控制事务）

    Returns:
        创建的 AuditLog 实例
    """
    site_group_id = tenant.site_group_id if tenant else None

    log_entry = AuditLog(
        user_id=user_id,
        site_group_id=site_group_id,
        host_id=host_id,
        action=action,
        ip_address=ip_address,
        user_agent=user_agent,
        success=success,
        details=details,
        result=result,
        content_type=content_type,
        object_id=object_id,
    )
    db.add(log_entry)
    if commit:
        await db.commit()
        await db.refresh(log_entry)
    return log_entry
