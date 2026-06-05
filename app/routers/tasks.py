"""
异步任务状态跟踪路由

包含任务列表和任务详情查询
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DBSession, PaginationParams
from app.models.task import AsyncTask, TaskProgress
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.task import AsyncTaskResponse

router = APIRouter()


@router.get(
    "/api/tasks",
    response_model=APIResponse[PaginatedResponse[AsyncTaskResponse]],
    tags=["tasks"],
)
async def list_tasks(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """列出异步任务"""
    count_stmt = select(func.count()).select_from(AsyncTask)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(AsyncTask)
        .order_by(AsyncTask.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    tasks = result.scalars().all()

    items = [AsyncTaskResponse.model_validate(t) for t in tasks]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.get(
    "/api/tasks/{task_id}",
    response_model=APIResponse[AsyncTaskResponse],
    tags=["tasks"],
)
async def get_task(
    task_id: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """获取任务详情和进度"""
    result = await db.execute(select(AsyncTask).where(AsyncTask.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    # 获取任务进度记录
    progress_stmt = (
        select(TaskProgress)
        .where(TaskProgress.task_id == task_id)
        .order_by(TaskProgress.timestamp.desc())
    )
    await db.execute(progress_stmt)

    task_resp = AsyncTaskResponse.model_validate(task)
    return APIResponse(data=task_resp)
