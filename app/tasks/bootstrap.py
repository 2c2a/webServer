"""
Bootstrap 任务模块

包含引导配置、证书签发、过期资源清理等任务
从 Celery shared_task 迁移至 Huey task
"""

import base64
import logging
import shutil
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.huey_config import huey
from app.models.bootstrap import ActiveSession, CertProvisionToken, InitialToken
from app.models.certificate import CertificateAuthority
from app.models.host import Host
from app.models.task import AsyncTask, TaskProgress

logger = logging.getLogger(__name__)

settings = get_settings()

# 同步数据库引擎（Huey 任务是同步的）
_sync_engine = None
_sync_session_factory = None


def _get_sync_session() -> Session:
    """获取同步数据库会话（Huey 任务使用）"""
    global _sync_engine, _sync_session_factory
    if _sync_engine is None:
        _sync_engine = create_engine(settings.database_url_sync)
        _sync_session_factory = sessionmaker(_sync_engine)
    return _sync_session_factory()


def _create_async_task(name: str, operator_id: str | None = None,
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
    )
    return async_task


def _start_task(async_task: AsyncTask, session: Session) -> None:
    """标记任务开始执行"""
    async_task.started_at = datetime.now(timezone.utc)
    session.add(async_task)
    session.commit()


def _complete_task(async_task: AsyncTask, session: Session,
                   result: dict | None = None) -> None:
    """标记任务成功完成"""
    async_task.status = "completed"
    async_task.progress = 100
    async_task.completed_at = datetime.now(timezone.utc)
    async_task.result = result
    session.add(async_task)
    session.commit()


def _fail_task(async_task: AsyncTask, session: Session,
               error_message: str) -> None:
    """标记任务失败"""
    async_task.status = "failed"
    async_task.completed_at = datetime.now(timezone.utc)
    async_task.error_message = error_message
    session.add(async_task)
    session.commit()


def _update_progress(async_task: AsyncTask, session: Session,
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


# ========== 清理任务 ==========

@huey.task()
def cleanup_expired_sessions() -> str:
    """清理过期的活动会话"""
    session = _get_sync_session()
    try:
        now = datetime.now(timezone.utc)
        count = session.query(ActiveSession).filter(
            ActiveSession.expires_at < now
        ).delete()
        session.commit()
        logger.info(f"清理了 {count} 个过期的活动会话")
        return f"清理了 {count} 个过期的活动会话"
    except Exception as e:
        session.rollback()
        logger.error(f"清理过期会话时出错: {e}")
        raise
    finally:
        session.close()


@huey.task()
def cleanup_expired_initial_tokens() -> str:
    """清理过期的初始令牌（7天前过期）"""
    session = _get_sync_session()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        count = session.query(InitialToken).filter(
            InitialToken.expires_at < cutoff
        ).delete()
        session.commit()
        logger.info(f"清理了 {count} 个过期的初始令牌")
        return f"清理了 {count} 个过期的初始令牌"
    except Exception as e:
        session.rollback()
        logger.error(f"清理过期初始令牌时出错: {e}")
        raise
    finally:
        session.close()


# ========== 引导配置任务 ==========

@huey.task()
def generate_bootstrap_config(hostname: str, ip_address: str,
                              operator_id: str | None = None) -> dict:
    """生成引导配置"""
    try:
        config = {
            "hostname": hostname,
            "ip_address": ip_address,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "success",
        }
        return {"success": True, "config": config}
    except Exception as e:
        logger.error(f"生成引导配置时出错: {e}")
        return {"success": False, "error": str(e)}


@huey.task()
def initialize_host_bootstrap(host_id: str,
                              operator_id: str | None = None) -> dict:
    """初始化主机引导"""
    session = _get_sync_session()
    try:
        host = session.query(Host).filter(Host.id == host_id).first()
        if not host:
            raise ValueError(f"主机 {host_id} 不存在")

        result = {
            "host_id": host_id,
            "hostname": host.hostname,
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        return result
    except Exception as e:
        logger.error(f"初始化主机引导时出错: {e}")
        raise
    finally:
        session.close()


# ========== 证书签发任务 ==========

@huey.task(retries=1, retry_delay=60)
def cert_provision_issue_certs(token_str: str) -> dict | None:
    """
    为证书配置令牌签发证书

    简化版：调用 cert_service 和 cert_storage 完成证书签发流程
    """
    from utils.cert_service import (
        generate_ca,
        issue_server_cert,
        issue_client_cert,
        generate_random_username,
        generate_random_password,
    )
    from utils.cert_storage import generate_cert_paths, save_cert_files

    session = _get_sync_session()
    try:
        provision_token = session.query(CertProvisionToken).filter(
            CertProvisionToken.token == token_str
        ).first()
        if not provision_token:
            return None

        if provision_token.status != "HOSTNAME_UPLOADED":
            return None

        host = provision_token.host
        hostname = host.hostname if host else provision_token.hostname
        if not hostname:
            return None

        ip_address = provision_token.ip_address or ""

        # 获取或创建 CA
        ca_obj = session.query(CertificateAuthority).filter(
            CertificateAuthority.is_active == True  # noqa: E712
        ).first()

        if not ca_obj:
            ca_key, ca_cert = generate_ca()
            ca_key_pem = ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM)

            from utils.cert_storage import save_ca_files, generate_ca_paths
            ca_root, ca_sub = generate_ca_paths()
            save_ca_files(ca_root, ca_sub, ca_key_pem, ca_cert_pem)

            ca_obj = CertificateAuthority(
                name="WinRM-CA",
                is_active=True,
                cert_root=ca_root,
                cert_sub=ca_sub,
                expires_at=datetime.now(timezone.utc) + timedelta(days=3650),
            )
            session.add(ca_obj)
            session.flush()

        # 从磁盘读取 CA 密钥和证书
        from utils.cert_storage import get_ca_file_paths
        ca_paths = get_ca_file_paths(ca_obj.cert_root, ca_obj.cert_sub)
        ca_key_path = ca_paths["key"]
        ca_cert_path = ca_paths["cert"]

        if not ca_key_path.exists() or not ca_cert_path.exists():
            logger.error(f"CA {ca_obj.name} key/cert 文件未找到")
            return None

        ca_key_pem = ca_key_path.read_bytes()
        ca_cert_pem = ca_cert_path.read_bytes()

        ca_key = cast(
            ec.EllipticCurvePrivateKey,
            serialization.load_pem_private_key(ca_key_pem, password=None),
        )
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem)

        # 生成 NTLM 回退凭据
        ntlm_user = generate_random_username()
        ntlm_password = generate_random_password()
        upn_value = f"{ntlm_user}@localhost"

        # 签发服务器证书
        server_result = issue_server_cert(
            ca_key=ca_key,
            ca_cert=ca_cert,
            hostname=hostname,
            ip_address=ip_address or None,
        )

        # 签发客户端证书
        client_key, client_cert = issue_client_cert(
            ca_key=ca_key,
            ca_cert=ca_cert,
            upn_value=upn_value,
        )

        # 保存证书文件
        cert_root, cert_sub = generate_cert_paths()

        ca_cert_pem_out = ca_cert.public_bytes(serialization.Encoding.PEM)
        client_cert_pem = client_cert.public_bytes(serialization.Encoding.PEM)
        client_key_pem = client_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        cert_dir = save_cert_files(
            cert_root=cert_root,
            cert_sub=cert_sub,
            ca_cert_pem=ca_cert_pem_out,
            client_cert_pem=client_cert_pem,
            server_pfx_bytes=server_result["pfx_data"],
            client_key_pem=client_key_pem,
        )

        # 更新主机记录
        if host:
            host.cert_root = cert_root
            host.cert_sub = cert_sub
            host._pfx_password = server_result["pfx_password"]
            host.ntlm_fallback_user = ntlm_user
            host._ntlm_fallback_password = ntlm_password
            host.cert_provision_status = "ready"
            host.cert_pem_path = str(cert_dir / "client.crt")
            host.cert_key_path = str(cert_dir / "client.key")
            host.auth_method = "certificate"
            host.use_ssl = True
            if host.port == 5985:
                host.port = 5986

        # 如果没有关联主机，将证书数据存入 token
        if not host:
            provision_token.cert_data = {
                "cert_root": cert_root,
                "cert_sub": cert_sub,
                "pfx_password": server_result["pfx_password"],
                "ntlm_user": ntlm_user,
                "ntlm_password": ntlm_password,
                "ca_cert_b64": base64.b64encode(ca_cert_pem_out).decode("utf-8"),
                "client_cert_b64": base64.b64encode(client_cert_pem).decode("utf-8"),
                "server_pfx_b64": base64.b64encode(
                    server_result["pfx_data"]
                ).decode("utf-8"),
            }

        provision_token.status = "CERT_ISSUED"
        session.commit()

        return {"success": True, "host_id": host.id if host else None}

    except Exception as e:
        session.rollback()
        logger.error(f"签发证书时出错: {e}", exc_info=True)
        raise
    finally:
        session.close()


# ========== 证书清理任务 ==========

@huey.task()
def cleanup_expired_provision_tokens() -> None:
    """清理过期的证书配置令牌"""
    session = _get_sync_session()
    try:
        now = datetime.now(timezone.utc)
        # 删除已过期的 ISSUED 状态 token
        session.query(CertProvisionToken).filter(
            CertProvisionToken.status == "ISSUED",
            CertProvisionToken.expires_at < now,
        ).delete()
        # 删除7天前过期的所有 token
        week_ago = now - timedelta(days=7)
        session.query(CertProvisionToken).filter(
            CertProvisionToken.expires_at < week_ago
        ).delete()
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"清理过期配置令牌时出错: {e}")
        raise
    finally:
        session.close()


@huey.task()
def cleanup_unactivated_certificates() -> None:
    """清理未激活的证书（pending/ready 超过60分钟）"""
    from utils.cert_storage import delete_cert_files

    session = _get_sync_session()
    try:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=60)
        hosts = session.query(Host).filter(
            Host.cert_provision_status.in_(["pending", "ready"]),
            Host.created_at < cutoff,
            Host.cert_activated_at.is_(None),
        ).all()

        for host in hosts:
            if host.cert_root and host.cert_sub:
                delete_cert_files(host.cert_root, host.cert_sub)
            host.cert_provision_status = "failed"
            host.cert_root = ""
            host.cert_sub = ""

        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"清理未激活证书时出错: {e}")
        raise
    finally:
        session.close()


@huey.task()
def cleanup_orphan_cert_dirs() -> None:
    """清理未被任何主机引用的孤立证书目录"""
    from utils.cert_storage import get_cert_base_dir

    session = _get_sync_session()
    try:
        base_dir = get_cert_base_dir()
        if not base_dir.exists():
            return

        # 收集所有活跃的证书路径
        active_paths = set()
        hosts_with_certs = session.query(Host).filter(
            Host.cert_root != "",
            Host.cert_sub != "",
        ).all()
        for host in hosts_with_certs:
            active_paths.add((host.cert_root, host.cert_sub))

        # 遍历目录，删除不在活跃路径中的
        for root_dir in base_dir.iterdir():
            if root_dir.is_dir() and len(root_dir.name) == 2:
                for sub_dir in list(root_dir.iterdir()):
                    if sub_dir.is_dir() and len(sub_dir.name) == 2:
                        if (root_dir.name, sub_dir.name) not in active_paths:
                            shutil.rmtree(sub_dir, ignore_errors=True)
                try:
                    root_dir.rmdir()
                except OSError:
                    logger.debug(
                        "跳过非空或不可访问的孤立证书根目录: %s",
                        root_dir,
                    )
    except Exception as e:
        logger.error(f"清理孤立证书目录时出错: {e}")
        raise
    finally:
        session.close()
