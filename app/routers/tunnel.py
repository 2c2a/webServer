"""
隧道客户端下载和配置路由

包含隧道客户端下载、配置获取、安装等
"""
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.dependencies import CurrentUser, DBSession, StaffUser
from app.models.host import Host
from app.schemas.common import APIResponse

router = APIRouter()


@router.get("/tunnel/download", tags=["tunnel"])
async def download_tunnel_client(
    request: Request,
    user: CurrentUser,
):
    """下载隧道客户端"""
    from pathlib import Path

    # 查找隧道客户端文件
    static_dir = Path("static/scripts")
    client_path = static_dir / "init.ps1"

    if not client_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="隧道客户端文件不存在",
        )

    return FileResponse(
        path=str(client_path),
        filename="tunnel-client.ps1",
        media_type="application/octet-stream",
    )


@router.post("/tunnel/config", response_model=APIResponse, tags=["tunnel"])
async def get_tunnel_config(
    host_id: str,
    db: DBSession = ...,
    user: CurrentUser = ...,
):
    """获取隧道配置"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    if not host.tunnel_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该主机未配置隧道",
        )

    config = {
        "tunnel_token": host.tunnel_token,
        "hostname": host.hostname,
        "rdp_port": host.rdp_port,
    }
    return APIResponse(data=config)


@router.post("/tunnel/install", response_model=APIResponse, tags=["tunnel"])
async def install_tunnel_service(
    host_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """安装隧道服务"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    if host.connection_type != "tunnel":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该主机不是隧道类型",
        )

    # TODO: 实现隧道服务安装逻辑
    return APIResponse(message="隧道服务安装任务已提交")
