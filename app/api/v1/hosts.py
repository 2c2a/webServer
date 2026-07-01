"""主机管理 API。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_staff
from app.core.db import get_db
from app.core.exceptions import NotFoundError
from app.models.host import Host
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext

router = APIRouter(prefix="/hosts", tags=["hosts"])


class HostOut(BaseModel):
    id: int
    name: str
    hostname: str
    connection_type: str
    auth_method: str
    port: int
    status: str
    os_version: str | None = None


class HostCreate(BaseModel):
    name: str
    hostname: str
    connection_type: str = "winrm"
    auth_method: str = "ntlm"
    port: int = 5985
    rdp_port: int = 3389
    use_ssl: bool = False
    username: str | None = None
    password: str | None = None
    description: str | None = None


class HostUpdate(BaseModel):
    name: str | None = None
    hostname: str | None = None
    connection_type: str | None = None
    auth_method: str | None = None
    port: int | None = None
    rdp_port: int | None = None
    use_ssl: bool | None = None
    username: str | None = None
    password: str | None = None
    description: str | None = None
    status: str | None = None


@router.get("", response_model=list[HostOut])
async def list_hosts(
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """列出主机（站点隔离）。"""
    filters = []
    if tenant.site_group_id and not user.is_superuser:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters).order_by(Host.id))
    hosts = result.scalars().all()
    return [
        HostOut(
            id=h.id, name=h.name, hostname=h.hostname,
            connection_type=h.connection_type, auth_method=h.auth_method,
            port=h.port, status=h.status, os_version=h.os_version,
        )
        for h in hosts
    ]


@router.post("", response_model=HostOut, status_code=201)
async def create_host(
    body: HostCreate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """创建主机（密码字段级加密存储）。"""
    from app.security.field_cipher import encrypt_field

    host = Host(
        name=body.name,
        hostname=body.hostname,
        connection_type=body.connection_type,
        auth_method=body.auth_method,
        port=body.port,
        rdp_port=body.rdp_port,
        use_ssl=body.use_ssl,
        username=body.username,
        password_cipher=encrypt_field(body.password, "host.password") if body.password else None,
        description=body.description,
        created_by_id=user.id,
        site_group_id=tenant.site_group_id,
        status="active",
    )
    db.add(host)
    await db.commit()
    await db.refresh(host)
    return HostOut(
        id=host.id, name=host.name, hostname=host.hostname,
        connection_type=host.connection_type, auth_method=host.auth_method,
        port=host.port, status=host.status, os_version=host.os_version,
    )


@router.get("/{host_id}", response_model=HostOut)
async def get_host(
    host_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """获取主机详情。"""
    filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")
    return HostOut(
        id=host.id, name=host.name, hostname=host.hostname,
        connection_type=host.connection_type, auth_method=host.auth_method,
        port=host.port, status=host.status, os_version=host.os_version,
    )


@router.put("/{host_id}", response_model=HostOut)
async def update_host(
    host_id: int,
    body: HostUpdate,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """更新主机信息。"""
    from app.security.field_cipher import encrypt_field

    filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")

    update_data = body.model_dump(exclude_unset=True)
    if "password" in update_data:
        password = update_data.pop("password")
        if password:
            update_data["password_cipher"] = encrypt_field(password, "host.password")

    for key, value in update_data.items():
        setattr(host, key, value)

    await db.commit()
    await db.refresh(host)
    return HostOut(
        id=host.id, name=host.name, hostname=host.hostname,
        connection_type=host.connection_type, auth_method=host.auth_method,
        port=host.port, status=host.status, os_version=host.os_version,
    )


@router.delete("/{host_id}")
async def delete_host(
    host_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """删除主机。"""
    filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        raise NotFoundError("主机不存在")
    await db.delete(host)
    await db.commit()
    return {"success": True}


@router.post("/{host_id}/test")
async def test_host_connection(
    host_id: int,
    user=Depends(require_staff),
    db: AsyncSession = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant),
):
    """测试主机连接（异步 WinRM，不阻塞）。"""
    from app.winrm import AsyncWinRMClient

    filters = [Host.id == host_id]
    if tenant.site_group_id and not user.is_superuser:
        filters.append(
            (Host.site_group_id == tenant.site_group_id)
            | (Host.site_group_id.is_(None))
        )
    result = await db.execute(select(Host).where(*filters))
    host = result.scalar_one_or_none()
    if host is None:
        return {"success": False, "error": "主机不存在"}

    client = await AsyncWinRMClient.from_host_config(host)
    try:
        res = await client.execute_command("whoami")
        return {
            "success": res.success,
            "output": res.std_out.strip(),
            "error": res.std_err,
            "demo_mode": res.demo_mode,
        }
    finally:
        await client.close()
