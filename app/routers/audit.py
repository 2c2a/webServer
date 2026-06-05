"""
审计日志路由

包含审计日志查看 API 和管理页面
"""
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.dependencies import DBSession, PaginationParams, StaffUser
from app.models.audit import AuditLog
from app.schemas.audit import AuditLogResponse
from app.schemas.common import APIResponse, PaginatedResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get(
    "/api/audit-logs",
    response_model=APIResponse[PaginatedResponse[AuditLogResponse]],
    tags=["audit"],
)
async def list_audit_logs(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出审计日志（管理员）"""
    count_stmt = select(func.count()).select_from(AuditLog)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    items = [AuditLogResponse.model_validate(log) for log in logs]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.get("/admin/audit", tags=["audit-pages"])
async def admin_audit_page(
    request: Request,
    user: StaffUser,
):
    """审计日志管理页面"""
    return templates.TemplateResponse("admin_base/audit/auditlog_list.html", {
        "request": request,
        "user": user,
    })
