"""主机相关异步任务（WinRM 操作不阻塞前端）。"""
from __future__ import annotations

from app.tasks.huey_app import huey


@huey.task()
async def configure_winrm_on_host(host_id: int, cert_data: dict | None = None) -> dict:
    """异步配置主机 WinRM（证书安装、认证切换等）。

    前端提交后立即返回任务 ID，不阻塞请求；任务在后台执行。
    """
    from app.core.db import AsyncSessionLocal
    from app.core.logging import get_logger
    from app.models.host import Host
    from app.security.field_cipher import decrypt_field
    from app.winrm import AsyncWinRMClient
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    log = get_logger(__name__)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Host).options(selectinload(Host.site_group)).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()
        if host is None:
            return {"success": False, "error": "主机不存在"}

        try:
            site_is_demo = host.site_group.is_demo if host.site_group else False
            client = await AsyncWinRMClient.from_host_config(host, site_is_demo=site_is_demo)
            # 示例：测试连接
            res = await client.execute_command("whoami")
            await client.close()
            log.info("winrm_configure_done", host_id=host_id, success=res.success)
            return {"success": res.success, "output": res.std_out.strip()}
        except Exception as e:  # noqa: BLE001
            log.exception("winrm_configure_failed", host_id=host_id)
            return {"success": False, "error": str(e)}


@huey.task()
async def install_certificates_on_host(host_id: int, cert_pem: str, key_pem: str) -> dict:
    """异步在远程主机安装证书。"""
    from app.core.db import AsyncSessionLocal
    from app.core.logging import get_logger
    from app.models.host import Host
    from app.winrm import AsyncWinRMClient
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    log = get_logger(__name__)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Host).options(selectinload(Host.site_group)).where(Host.id == host_id)
        )
        host = result.scalar_one_or_none()
        if host is None:
            return {"success": False, "error": "主机不存在"}
        try:
            site_is_demo = host.site_group.is_demo if host.site_group else False
            client = await AsyncWinRMClient.from_host_config(host, site_is_demo=site_is_demo)
            # 通过 PowerShell here-string 写入证书文件并导入
            script = f"""
$certPem = @'
{cert_pem}
'@
Set-Content -Path $env:TEMP\\cert.pem -Value $certPem -Encoding ASCII
Import-Certificate -FilePath $env:TEMP\\cert.pem -CertStoreLocation Cert:\\LocalMachine\\My
"""
            res = await client.execute_powershell(script)
            await client.close()
            return {"success": res.success, "output": res.std_out, "error": res.std_err}
        except Exception as e:  # noqa: BLE001
            log.exception("cert_install_failed", host_id=host_id)
            return {"success": False, "error": str(e)}


@huey.task()
async def cleanup_expired_sessions() -> int:
    """定时清理过期会话（每日执行）。"""
    from datetime import datetime, timezone

    from app.core.db import AsyncSessionLocal
    from app.core.logging import get_logger
    from app.models.bootstrap import ActiveSession
    from sqlalchemy import delete

    log = get_logger(__name__)
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            delete(ActiveSession).where(ActiveSession.expires_at < now)
        )
        await db.commit()
        count = result.rowcount or 0
        log.info("sessions_cleaned", count=count)
        return count
