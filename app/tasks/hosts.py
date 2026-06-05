"""
Host 任务模块

包含主机 WinRM 配置、连接测试、证书安装等任务
从 Celery shared_task 迁移至 Huey task
"""

import logging
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.huey_config import huey
from app.models.host import Host
from app.models.task import AsyncTask, TaskProgress

logger = logging.getLogger(__name__)

settings = get_settings()

# 同步数据库引擎
_sync_engine = None
_sync_session_factory = None


def _get_sync_session() -> Session:
    """获取同步数据库会话（Huey 任务使用）"""
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync)
        _sync_session_factory = sessionmaker(_sync_engine)
    return _sync_session_factory()


# ========== 输入验证 ==========

CERT_THUMBPRINT_PATTERN = re.compile(r"^[A-Fa-f0-9]{40}$")
CERT_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]{1,255}\.pem$")


def _validate_cert_thumbprint(thumbprint: str) -> str:
    """验证证书指纹格式"""
    if not thumbprint:
        raise ValueError("证书指纹不能为空")
    thumbprint = thumbprint.strip().upper()
    if not CERT_THUMBPRINT_PATTERN.match(thumbprint):
        raise ValueError("证书指纹格式无效，必须是40位十六进制字符")
    return thumbprint


def _validate_cert_filename(filename: str) -> str:
    """验证证书文件名格式"""
    if not filename:
        raise ValueError("证书文件名不能为空")
    if not CERT_FILENAME_PATTERN.match(filename):
        raise ValueError(
            "证书文件名格式无效，只允许字母、数字、下划线、连字符和点，且必须以.pem结尾"
        )
    return filename


def _validate_cert_content(content: str) -> str:
    """验证证书内容"""
    if not content:
        raise ValueError("证书内容不能为空")
    if '@"' in content or '"@' in content:
        raise ValueError("证书内容包含非法字符")
    if len(content) > 100000:
        raise ValueError("证书内容过长")
    return content


# ========== AsyncTask 辅助函数 ==========

def _create_async_task(session: Session, name: str,
                       operator_id: str | None = None,
                       target_object_id: int | None = None,
                       target_content_type: str | None = None) -> AsyncTask:
    """创建 AsyncTask 跟踪记录"""
    task_id = str(uuid4())
    async_task = AsyncTask(
        id=str(uuid4()),
        task_id=task_id,
        name=name,
        created_by_id=operator_id,
        target_object_id=target_object_id,
        target_content_type=target_content_type,
        status="running",
        started_at=datetime.now(timezone.utc),
    )
    session.add(async_task)
    session.commit()
    return async_task


def _update_progress(session: Session, async_task: AsyncTask,
                     progress: int, message: str | None = None) -> None:
    """更新任务进度"""
    async_task.progress = progress
    session.add(async_task)
    if message:
        progress_record = TaskProgress(
            id=str(uuid4()),
            task_id=async_task.id,
            progress=progress,
            message=message,
        )
        session.add(progress_record)
    session.commit()


def _complete_success(session: Session, async_task: AsyncTask,
                      result: dict | None = None) -> None:
    """标记任务成功完成"""
    async_task.status = "completed"
    async_task.progress = 100
    async_task.completed_at = datetime.now(timezone.utc)
    async_task.result = result
    session.add(async_task)
    session.commit()


def _complete_failure(session: Session, async_task: AsyncTask,
                      error_message: str) -> None:
    """标记任务失败"""
    async_task.status = "failed"
    async_task.completed_at = datetime.now(timezone.utc)
    async_task.error_message = error_message
    session.add(async_task)
    session.commit()


# ========== WinRM 客户端辅助 ==========

def _get_host_client(host: Host):
    """根据主机配置获取 WinRM 客户端"""
    from utils.winrm_client import WinrmClient

    if host.auth_method == "certificate" and host.cert_pem_path and host.cert_key_path:
        return WinrmClient(
            hostname=host.hostname,
            port=host.port,
            use_ssl=host.use_ssl,
            auth_method="certificate",
            cert_pem_path=host.cert_pem_path,
            cert_key_path=host.cert_key_path,
            server_cert_validation="validate",
            ca_trust_path=_get_ca_cert_path(host) if host.cert_root else None,
        )
    else:
        from utils.crypto import decrypt_value
        password = decrypt_value(host._password) if host._password else ""
        return WinrmClient(
            hostname=host.hostname,
            port=host.port,
            username=host.username,
            password=password,
            use_ssl=host.use_ssl,
            auth_method="ntlm",
        )


def _get_ca_cert_path(host: Host):
    """获取主机对应的 CA 证书路径"""
    from utils.cert_storage import get_cert_dir
    from pathlib import Path
    cert_dir = get_cert_dir(host.cert_root, host.cert_sub)
    return str(cert_dir / "ca.crt")


# ========== WinRM 配置任务 ==========

@huey.task(retries=2, retry_delay=30)
def configure_winrm_on_host(host_id: str, cert_thumbprint: str | None = None,
                            operator_id: str | None = None) -> dict:
    """配置主机 WinRM 服务"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"配置WinRM - 主机 #{host_id}",
            operator_id=operator_id,
            target_object_id=host_id,
            target_content_type="hosts.Host",
        )

        host = session.query(Host).filter(Host.id == host_id).first()
        if not host:
            _complete_failure(session, async_task, f"主机 {host_id} 不存在")
            return {"success": False, "error": "主机不存在"}

        _update_progress(session, async_task, 10, "开始配置WinRM")

        try:
            from utils.winrm_client import WinrmClient

            client = _get_host_client(host)

            actual_thumbprint = cert_thumbprint
            if actual_thumbprint:
                actual_thumbprint = _validate_cert_thumbprint(actual_thumbprint)

            ps_script = """
Enable-PSRemoting -Force
Set-Service -Name WinRM -StartupType Automatic
"""

            if actual_thumbprint:
                ps_script += f"""
$selectorset = @{{Transport="HTTPS"}}
$resourceset = @{{Port="5986"; CertificateThumbprint="{actual_thumbprint}"}}
Get-WSManInstance -ResourceURI winrm/config/listener -SelectorSet $selectorset -ErrorAction SilentlyContinue | Remove-WSManInstance -ErrorAction SilentlyContinue
New-WSManInstance -ResourceURI winrm/config/listener -SelectorSet $selectorset -ValueSet $resourceset
if (-not (Get-NetFirewallRule -Name "WinRM-HTTPS-In-TCP-Public" -ErrorAction SilentlyContinue)) {{
    New-NetFirewallRule -Name "WinRM-HTTPS-In-TCP-Public" -DisplayName "WinRM HTTPS Inbound" -Enabled True -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow -Profile Public,Private,Domain
}}
"""

            ps_script += """
Set-Item -Path "WSMan:\\localhost\\Service\\AllowUnencrypted" -Value $false
Set-Item -Path "WSMan:\\localhost\\Service\\Auth\\Basic" -Value $true
Restart-Service WinRM
"""

            _update_progress(session, async_task, 30, "执行WinRM配置脚本")

            result = client.execute_powershell(ps_script)

            if result.status_code == 0:
                _update_progress(session, async_task, 80, "配置脚本执行成功")

                host.status = "online"
                if cert_thumbprint:
                    # 保存证书指纹（如果有对应字段）
                    pass
                session.commit()

                _complete_success(session, async_task, {
                    "status_code": result.status_code,
                    "stdout": result.std_out,
                    "success": True,
                })

                return {
                    "success": True,
                    "status_code": result.status_code,
                    "host_id": host_id,
                }
            else:
                error_msg = result.std_err if result.std_err else "Unknown error"
                _complete_failure(
                    session, async_task,
                    f"PowerShell 脚本执行失败: {error_msg}",
                )
                return {
                    "success": False,
                    "status_code": result.status_code,
                    "error": error_msg,
                }

        except Exception as conn_error:
            logger.error(f"连接主机失败: {conn_error}", exc_info=True)
            _complete_failure(
                session, async_task,
                f"无法连接到主机: {conn_error}",
            )
            return {"success": False, "error": str(conn_error)}

    except Exception as e:
        logger.error(f"配置WinRM失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"配置WinRM - 主机 #{host_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 连接测试任务 ==========

@huey.task(retries=1, retry_delay=30)
def test_winrm_connection(host_id: str,
                          use_certificate_auth: bool = False) -> dict:
    """测试主机的 WinRM 连接"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"测试WinRM连接 - 主机 #{host_id}",
            target_object_id=host_id,
            target_content_type="hosts.Host",
        )

        host = session.query(Host).filter(Host.id == host_id).first()
        if not host:
            _complete_failure(session, async_task, f"主机 {host_id} 不存在")
            return {"success": False, "error": "主机不存在"}

        old_status = host.status

        try:
            client = _get_host_client(host)
            result = client.execute_command("whoami")

            if result.success:
                new_status = "online"
                host.status = new_status

                # 如果是证书认证且证书状态为 pending/ready，更新为 configured
                if host.auth_method == "certificate" and host.cert_provision_status in ("pending", "ready"):
                    host.cert_provision_status = "configured"
                    host.cert_activated_at = datetime.now(timezone.utc)

                session.commit()

                _complete_success(session, async_task, {
                    "connected": True,
                    "status": new_status,
                    "old_status": old_status,
                    "message": f"连接成功，主机状态: {new_status}",
                })

                return {
                    "success": True,
                    "connected": True,
                    "status": new_status,
                }
            else:
                new_status = "offline"
                host.status = new_status

                if host.auth_method == "certificate" and host.cert_provision_status in ("pending", "ready"):
                    host.cert_provision_status = "failed"

                session.commit()

                _complete_failure(
                    session, async_task,
                    f"连接测试失败，主机状态: {new_status}",
                )
                return {
                    "success": False,
                    "connected": False,
                    "status": new_status,
                    "error": f"连接失败，主机状态: {new_status}",
                }

        except Exception as conn_error:
            host.status = "error"
            if host.auth_method == "certificate" and host.cert_provision_status in ("pending", "ready"):
                host.cert_provision_status = "failed"
            session.commit()
            raise

    except Exception as e:
        logger.error(f"测试WinRM连接失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"测试WinRM连接 - 主机 #{host_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "connected": False, "error": str(e)}
    finally:
        session.close()


@huey.task(retries=1, retry_delay=30)
def test_winrm_connection_raw(connection_type: str, hostname: str, port: int,
                              use_ssl: bool, auth_method: str,
                              username: str, password: str) -> dict:
    """测试原始 WinRM 连接参数"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"测试WinRM连接 - {hostname}",
        )

        try:
            if connection_type == "localwinserver":
                from utils.local_winserver_client import LocalWinServerClient
                client = LocalWinServerClient(
                    username=username,
                    password=password,
                )
                result = client.execute_command("echo Connection Test OK")
            elif connection_type == "winrm" and auth_method == "ntlm":
                from utils.winrm_client import WinrmClient
                client = WinrmClient(
                    hostname=hostname,
                    port=int(port),
                    username=username,
                    password=password,
                    use_ssl=bool(use_ssl),
                    auth_method="ntlm",
                )
                result = client.execute_command("whoami")
            else:
                raise ValueError(f"不支持的连接类型: {connection_type}")

            if result.success:
                output = result.std_out.strip() if result.std_out else ""
                _complete_success(session, async_task, {
                    "connected": True,
                    "output": output,
                    "message": f"连接成功{f' ({output})' if output else ''}",
                })
                return {
                    "success": True,
                    "connected": True,
                    "output": output,
                    "message": f"连接成功{f' ({output})' if output else ''}",
                }
            else:
                error_detail = (
                    result.std_err.strip()
                    if result.std_err
                    else f"命令执行返回非零状态码: {result.status_code}"
                )
                _complete_failure(session, async_task, f"连接失败: {error_detail}")
                return {
                    "success": False,
                    "connected": False,
                    "error": f"连接失败: {error_detail}",
                }

        except Exception as conn_error:
            logger.error(f"测试WinRM连接失败: {hostname}, 错误: {conn_error}", exc_info=True)
            _complete_failure(session, async_task, str(conn_error))
            return {
                "success": False,
                "connected": False,
                "error": f"连接测试失败: {conn_error}",
            }

    except Exception as e:
        logger.error(f"测试WinRM连接失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"测试WinRM连接 - {hostname}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "connected": False, "error": str(e)}
    finally:
        session.close()


# ========== 证书安装任务 ==========

@huey.task(retries=2, retry_delay=30)
def install_certificates_on_host(host_id: str, cert_pem: str,
                                 cert_filename: str,
                                 operator_id: str | None = None) -> dict:
    """在主机上安装证书"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"安装证书 - 主机 #{host_id}",
            operator_id=operator_id,
            target_object_id=host_id,
            target_content_type="hosts.Host",
        )

        host = session.query(Host).filter(Host.id == host_id).first()
        if not host:
            _complete_failure(session, async_task, f"主机 {host_id} 不存在")
            return {"success": False, "error": "主机不存在"}

        # 验证输入
        cert_filename = _validate_cert_filename(cert_filename)
        cert_pem = _validate_cert_content(cert_pem)

        from utils.winrm_client import WinrmClient, _escape_for_here_string

        client = _get_host_client(host)

        safe_cert_content = _escape_for_here_string(cert_pem)
        safe_filename = cert_filename.replace('"', '').replace("'", "").replace(";", "")

        ps_script = f"""
$tempDir = "$env:TEMP\\2c2a_Certs"
if (!(Test-Path $tempDir)) {{
    New-Item -ItemType Directory -Path $tempDir -Force
}}

$certContent = @"
{safe_cert_content}
"@

$certPath = Join-Path $tempDir "{safe_filename}"
$certContent | Out-File -FilePath $certPath -Encoding UTF8

Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\\LocalMachine\\Root
Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\\LocalMachine\\My

Write-Output "Certificate installed successfully"

Remove-Item $tempDir -Recurse -Force
"""

        result = client.execute_powershell(ps_script)

        if result.status_code == 0:
            _complete_success(session, async_task, {
                "installed": True,
                "cert_filename": cert_filename,
                "output": result.std_out,
            })
            return {"success": True, "installed": True}
        else:
            error_msg = result.std_err if result.std_err else "Unknown error"
            _complete_failure(
                session, async_task,
                f"证书安装失败: {error_msg}",
            )
            return {
                "success": False,
                "installed": False,
                "error": error_msg,
            }

    except Exception as e:
        logger.error(f"安装证书失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"安装证书 - 主机 #{host_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()
