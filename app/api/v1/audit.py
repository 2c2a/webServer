"""审计 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_staff
from app.core.db import get_db
from app.models.audit import AuditLog
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/logs")
async def list_audit_logs(
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
    limit: int = Query(50, ge=1, le=500),
    action: str | None = None,
    success: bool | None = None,
):
    """列出审计日志（租户隔离）。

    - 超级管理员可查看全部审计日志
    - 租户管理员仅能查看本站点组的审计日志及全局日志（site_group_id 为 NULL）
    """
    query = select(AuditLog).order_by(AuditLog.timestamp.desc())

    # 租户隔离：非超级用户仅可见本站点组数据
    if not user.is_superuser:
        if tenant.site_group_id:
            query = query.where(
                (AuditLog.site_group_id == tenant.site_group_id)
                | (AuditLog.site_group_id.is_(None))
            )
        else:
            # 无站点组上下文的非超管用户，返回空结果
            query = query.where(AuditLog.id == -1)

    # 可选过滤条件
    if action:
        query = query.where(AuditLog.action == action)
    if success is not None:
        query = query.where(AuditLog.success == success)

    query = query.limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "action": l.action,
            "ip_address": l.ip_address,
            "success": l.success,
            "timestamp": l.timestamp.isoformat() if l.timestamp else None,
            "site_group_id": l.site_group_id,
        }
        for l in logs
    ]
