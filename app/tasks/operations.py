"""
Operations 任务模块

包含开户处理、云电脑用户管理、RDP域名管理等任务
从 Celery shared_task 迁移至 Huey task
"""

import logging
import secrets
import string
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.huey_config import huey
from app.models.host import Host
from app.models.product import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    RdpDomainRoute,
)
from app.models.task import AsyncTask, TaskProgress
from app.models.user import User

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


def _generate_secure_password(length: int = 16) -> str:
    """生成安全密码"""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password)
        if has_upper and has_lower and has_digit and has_special:
            return password


def _create_async_task(session: Session, name: str,
                       operator_id: str | None = None,
                       target_object_id: int | None = None,
                       target_content_type: str | None = None) -> AsyncTask:
    """创建 AsyncTask 跟踪记录并持久化"""
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
            ca_trust_path=str(
                _get_ca_cert_path(host.cert_root, host.cert_sub)
            ) if host.cert_root else None,
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


def _get_ca_cert_path(cert_root: str, cert_sub: str):
    """获取 CA 证书路径"""
    from utils.cert_storage import get_cert_dir
    cert_dir = get_cert_dir(cert_root, cert_sub)
    return cert_dir / "ca.crt"


def _rollback_opening_request(session: Session, request_id: str) -> None:
    """回滚开户请求"""
    try:
        request_obj = session.query(AccountOpeningRequest).filter(
            AccountOpeningRequest.id == request_id
        ).first()
        if not request_obj:
            return

        host = request_obj.target_product.host if request_obj.target_product else None
        if host and request_obj.username:
            client = _get_host_client(host)
            result = client.disabled_user(request_obj.username)
            if result.success:
                logger.info(f"已禁用用户 {request_obj.username}")
            else:
                logger.warning(f"禁用用户失败: {result.std_err}")

        request_obj.status = "pending"
        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"回滚操作失败: {e}")


# ========== 开户处理任务 ==========

@huey.task(retries=1, retry_delay=60)
def process_opening_request(request_id: str,
                            operator_id: str | None = None) -> dict:
    """处理开户请求"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"处理开户请求 #{request_id}",
            operator_id=operator_id,
            target_object_id=request_id,
            target_content_type="operations.AccountOpeningRequest",
        )

        request_obj = session.query(AccountOpeningRequest).filter(
            AccountOpeningRequest.id == request_id
        ).first()
        if not request_obj:
            _complete_failure(session, async_task, f"开户请求 {request_id} 不存在")
            return {"success": False, "error": "请求不存在"}

        _update_progress(session, async_task, 10, "开始处理开户请求")

        # 获取目标产品关联的主机
        product = request_obj.target_product
        if not product:
            raise Exception("没有关联的产品")
        host = product.host
        if not host:
            raise Exception("产品没有关联的主机")

        _update_progress(session, async_task, 30, "找到可用主机")

        username = request_obj.username
        password = _generate_secure_password()

        _update_progress(session, async_task, 50, "执行PowerShell命令创建用户")

        client = _get_host_client(host)
        result = client.create_user(
            username=username,
            password=password,
            description=request_obj.user_description or "Cloud computer user",
        )

        if result.status_code != 0:
            error_msg = result.std_err if result.std_err else "Unknown error"
            raise Exception(f"创建用户失败: {error_msg}")

        _update_progress(session, async_task, 70, "用户创建成功")

        # 设置磁盘配额
        user_disk_quota = {}
        if product.enable_disk_quota and product.default_disk_quota:
            user_disk_quota = dict(product.default_disk_quota)
            if request_obj.requested_disk_capacity:
                for disk, capacity in request_obj.requested_disk_capacity.items():
                    if disk in (product.allow_extra_quota_disks or []):
                        user_disk_quota[disk] = capacity

        if user_disk_quota:
            try:
                from utils.disk_quota import set_user_disk_quotas
                quota_result = set_user_disk_quotas(
                    client, username, user_disk_quota
                )
                if not quota_result["success"]:
                    logger.warning(f"磁盘配额设置部分失败: {quota_result.get('errors', [])}")
            except Exception as e:
                logger.error(f"磁盘配额设置失败: {e}")

        # 更新请求状态
        request_obj.status = "approved"
        request_obj.cloud_user_id = username
        from utils.crypto import encrypt_value
        request_obj.cloud_user_password = encrypt_value(password)

        # 创建云电脑用户记录
        cloud_user = CloudComputerUser(
            id=str(uuid4()),
            username=username,
            fullname=request_obj.user_fullname,
            email=request_obj.user_email,
            description=request_obj.user_description,
            product_id=product.id,
            status="active",
            disk_quota=user_disk_quota,
            created_from_request_id=request_obj.id,
            owner_id=request_obj.applicant_id,
            _initial_password=encrypt_value(password),
        )
        session.add(cloud_user)

        _update_progress(session, async_task, 90, "更新请求状态")

        result_data = {
            "host": host.hostname,
            "username": username,
            "success": True,
            "cloud_user_id": cloud_user.id,
        }
        _complete_success(session, async_task, result_data)

        return result_data

    except Exception as e:
        logger.error(f"处理开户请求失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"处理开户请求 #{request_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass

        try:
            _rollback_opening_request(session, request_id)
        except Exception as rollback_error:
            logger.error(f"回滚开户请求失败: {rollback_error}", exc_info=True)

        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 远程管理任务 ==========

@huey.task(retries=2, retry_delay=30)
def remote_set_admin(cloud_user_id: str,
                     operator_id: str | None = None) -> dict:
    """远程设置云电脑用户为管理员"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"设置管理员 - 用户 #{cloud_user_id}",
            operator_id=operator_id,
            target_object_id=cloud_user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == cloud_user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {cloud_user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)
        client.op_user(cloud_user.username)

        cloud_user.is_admin = True
        session.commit()

        _complete_success(session, async_task, {
            "username": cloud_user.username,
            "is_admin": True,
        })
        return {"success": True, "username": cloud_user.username}

    except Exception as e:
        logger.error(f"远程设置管理员失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"设置管理员 - 用户 #{cloud_user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


@huey.task(retries=2, retry_delay=30)
def remote_remove_admin(cloud_user_id: str,
                        operator_id: str | None = None) -> dict:
    """远程移除云电脑用户管理员权限"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"取消管理员 - 用户 #{cloud_user_id}",
            operator_id=operator_id,
            target_object_id=cloud_user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == cloud_user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {cloud_user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)
        client.deop_user(cloud_user.username)

        cloud_user.is_admin = False
        session.commit()

        _complete_success(session, async_task, {
            "username": cloud_user.username,
            "is_admin": False,
        })
        return {"success": True, "username": cloud_user.username}

    except Exception as e:
        logger.error(f"远程取消管理员失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"取消管理员 - 用户 #{cloud_user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


@huey.task(retries=2, retry_delay=30)
def remote_reset_windows_password(cloud_user_id: str, new_password: str,
                                  operator_id: str | None = None) -> dict:
    """远程重置 Windows 密码"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"重置Windows密码 - 用户 #{cloud_user_id}",
            operator_id=operator_id,
            target_object_id=cloud_user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == cloud_user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {cloud_user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)
        result = client.reset_password(cloud_user.username, new_password)

        if result.status_code != 0:
            error_msg = result.std_err if result.std_err else "Unknown error"
            raise Exception(f"重置密码失败: {error_msg}")

        _complete_success(session, async_task, {"username": cloud_user.username})
        return {"success": True, "username": cloud_user.username}

    except Exception as e:
        logger.error(f"远程重置密码失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"重置Windows密码 - 用户 #{cloud_user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


@huey.task(retries=2, retry_delay=30)
def remote_set_disk_quota(cloud_user_id: str, disk: str, quota_mb: int,
                          operator_id: str | None = None) -> dict:
    """远程设置磁盘配额"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"设置磁盘配额 - 用户 #{cloud_user_id}",
            operator_id=operator_id,
            target_object_id=cloud_user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == cloud_user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {cloud_user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        from utils.disk_quota import set_disk_quota_via_client
        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)
        result = set_disk_quota_via_client(client, cloud_user.username, disk, quota_mb)

        if result["success"]:
            _complete_success(session, async_task, result)
            return result
        else:
            _complete_failure(session, async_task, result.get("message", "设置配额失败"))
            return result

    except Exception as e:
        logger.error(f"远程设置磁盘配额失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"设置磁盘配额 - 用户 #{cloud_user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


@huey.task(retries=2, retry_delay=30)
def remote_set_user_disk_quotas(cloud_user_id: str, disk_quota: dict,
                                operator_id: str | None = None) -> dict:
    """远程批量设置用户磁盘配额"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"设置用户磁盘配额 - 用户 #{cloud_user_id}",
            operator_id=operator_id,
            target_object_id=cloud_user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == cloud_user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {cloud_user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        from utils.disk_quota import set_user_disk_quotas
        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)
        result = set_user_disk_quotas(client, cloud_user.username, disk_quota)

        if result["success"]:
            _complete_success(session, async_task, result)
            return result
        else:
            _complete_failure(
                session, async_task,
                "; ".join(result.get("errors", ["设置配额失败"])),
            )
            return result

    except Exception as e:
        logger.error(f"远程设置用户磁盘配额失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"设置用户磁盘配额 - 用户 #{cloud_user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


@huey.task()
def remote_get_disk_info(host_id: str,
                         operator_id: str | None = None) -> dict:
    """远程获取主机磁盘信息"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"获取磁盘信息 - 主机 #{host_id}",
            operator_id=operator_id,
            target_object_id=host_id,
            target_content_type="hosts.Host",
        )

        host = session.query(Host).filter(Host.id == host_id).first()
        if not host:
            _complete_failure(session, async_task, f"主机 {host_id} 不存在")
            return {"success": False, "error": "主机不存在"}

        from utils.disk_quota import get_disk_info_via_client
        client = _get_host_client(host)
        disks = get_disk_info_via_client(client)

        _complete_success(session, async_task, {"disks": disks})
        return {"success": True, "data": disks}

    except Exception as e:
        logger.error(f"远程获取磁盘信息失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"获取磁盘信息 - 主机 #{host_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 云用户远程操作任务 ==========

@huey.task(retries=3, retry_delay=30)
def execute_cloud_user_remote_action(user_id: str, action: str) -> dict:
    """
    异步执行云电脑用户的远程操作（禁用/启用/删除）
    将远程 WinRM 调用从 save() 中解耦，避免阻塞数据库事务
    """
    session = _get_sync_session()
    try:
        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == user_id
        ).first()
        if not cloud_user:
            logger.error(f"CloudComputerUser pk={user_id} 不存在，跳过远程操作 '{action}'")
            return {"success": False, "error": f"用户 {user_id} 不存在"}

        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)

        if action == "disable":
            result = client.disabled_user(cloud_user.username)
            if result.success:
                cloud_user.status = "disabled"
                session.commit()
        elif action == "enable":
            result = client.enable_user(cloud_user.username)
            if result.success:
                cloud_user.status = "active"
                session.commit()
        elif action == "delete":
            result = client.delete_user(cloud_user.username)
            if result.success:
                cloud_user.status = "deleted"
                session.commit()
        else:
            logger.error(f"未知远程操作 '{action}'，用户 {cloud_user.username}")
            return {"success": False, "error": f"未知操作: {action}"}

        if not result.success:
            logger.warning(
                f"远程操作 '{action}' 执行失败，用户 {cloud_user.username}: {result.std_err}"
            )
            return {"success": False, "error": result.std_err}

        return {"success": True, "action": action, "user_id": user_id}

    except Exception as e:
        session.rollback()
        logger.error(f"执行远程操作失败: {e}", exc_info=True)
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 开户创建任务 ==========

@huey.task(retries=2, retry_delay=60)
def process_account_creation(request_id: str) -> dict:
    """
    异步处理开户请求的用户创建流程
    将远程 WinRM 调用从 AccountOpeningRequest.save() 中解耦
    """
    session = _get_sync_session()
    try:
        request_obj = session.query(AccountOpeningRequest).filter(
            AccountOpeningRequest.id == request_id
        ).first()
        if not request_obj:
            logger.error(f"AccountOpeningRequest pk={request_id} 不存在")
            return {"success": False, "error": f"请求 {request_id} 不存在"}

        # 委托给 process_opening_request 的核心逻辑
        # 这里简化为直接调用
        result = process_opening_request(request_id)
        return result

    except Exception as e:
        logger.error(f"开户创建失败，请求 {request_id}: {e}", exc_info=True)
        try:
            request_obj = session.query(AccountOpeningRequest).filter(
                AccountOpeningRequest.id == request_id
            ).first()
            if request_obj and request_obj.status not in ("completed", "failed"):
                request_obj.status = "failed"
                request_obj.result_message = f"异步处理异常: {e}"
                session.commit()
        except Exception as save_err:
            session.rollback()
            logger.error(f"更新请求状态失败: {save_err}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== RDP 域名任务 ==========

@huey.task()
def cleanup_expired_rdp_domains() -> dict:
    """停用过期的 RDP 域名路由"""
    session = _get_sync_session()
    try:
        now = datetime.now(timezone.utc)
        expired_routes = session.query(RdpDomainRoute).filter(
            RdpDomainRoute.is_active == True,  # noqa: E712
            RdpDomainRoute.expires_at < now,
        ).all()

        cleaned = 0
        for route in expired_routes:
            route.is_active = False
            cleaned += 1

        session.commit()
        logger.info(f"清理了 {cleaned} 个过期的 RDP 域名路由")
        return {"cleaned": cleaned}

    except Exception as e:
        session.rollback()
        logger.error(f"清理过期RDP域名时出错: {e}")
        raise
    finally:
        session.close()


@huey.task()
def allocate_rdp_domain(user_id: str, product_id: str) -> dict:
    """为用户分配 RDP 域名"""
    session = _get_sync_session()
    try:
        user = session.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": f"用户 {user_id} 不存在"}

        product = session.query(Product).filter(Product.id == product_id).first()
        if not product:
            return {"success": False, "error": f"产品 {product_id} 不存在"}

        host = product.host
        if not product.enable_host_protection:
            return {
                "success": False,
                "error": "该产品未启用主机保护",
            }

        if host.connection_type != "tunnel" or not host.tunnel_token:
            return {
                "success": False,
                "error": "主机不是隧道主机",
            }

        # 生成域名
        import secrets as _secrets
        domain_prefix = _secrets.token_hex(4)
        from app.config import get_settings
        _settings = get_settings()
        domain = f"{domain_prefix}.{_settings.rdp_domain}"

        route = RdpDomainRoute(
            id=str(uuid4()),
            domain=domain,
            product_id=product.id,
            assigned_to_id=user.id,
            tunnel_token=host.tunnel_token,
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        session.add(route)
        session.commit()

        return {
            "success": True,
            "domain": domain,
            "expires_at": route.expires_at.isoformat(),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"RDP域名分配失败: {e}")
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 密码重置任务 ==========

@huey.task(retries=2, retry_delay=30)
def reset_user_password(user_id: str,
                        operator_id: str | None = None) -> dict:
    """重置云电脑用户密码"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"重置用户密码 - 用户 #{user_id}",
            operator_id=operator_id,
            target_object_id=user_id,
            target_content_type="operations.CloudComputerUser",
        )

        cloud_user = session.query(CloudComputerUser).filter(
            CloudComputerUser.id == user_id
        ).first()
        if not cloud_user:
            _complete_failure(session, async_task, f"用户 {user_id} 不存在")
            return {"success": False, "error": "用户不存在"}

        new_password = _generate_secure_password()

        product = cloud_user.product
        host = product.host
        client = _get_host_client(host)

        result = client.reset_password(cloud_user.username, new_password)

        if result.status_code != 0:
            error_msg = result.std_err if result.std_err else "Unknown error"
            raise Exception(f"重置密码失败: {error_msg}")

        # 更新存储的密码
        from utils.crypto import encrypt_value
        if cloud_user.created_from_request:
            cloud_user.created_from_request.cloud_user_password = encrypt_value(new_password)
        cloud_user._initial_password = encrypt_value(new_password)
        cloud_user.password_viewed = False
        cloud_user.password_viewed_at = None
        session.commit()

        _complete_success(session, async_task, {
            "success": True,
            "message": "密码重置成功",
            "username": cloud_user.username,
        })

        return {
            "success": True,
            "message": "密码重置成功",
            "username": cloud_user.username,
        }

    except Exception as e:
        logger.error(f"重置密码失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"重置用户密码 - 用户 #{user_id}",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 批量处理任务 ==========

@huey.task()
def batch_process_opening_requests(request_ids: list[str],
                                   operator_id: str | None = None) -> dict:
    """批量处理开户请求"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"批量处理开户请求 ({len(request_ids)}个)",
            operator_id=operator_id,
        )

        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "errors": [],
        }

        total_requests = len(request_ids)

        for idx, request_id in enumerate(request_ids):
            try:
                progress = int((idx / total_requests) * 80) + 10
                _update_progress(
                    session, async_task, progress,
                    f"处理第 {idx + 1}/{total_requests} 个请求",
                )

                # 同步调用单个处理任务
                result = process_opening_request(request_id, operator_id)

                results["processed"] += 1
                if result.get("success"):
                    results["successful"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append({
                        "request_id": request_id,
                        "error": result.get("error", "Unknown error"),
                    })

            except Exception as e:
                results["failed"] += 1
                results["errors"].append({
                    "request_id": request_id,
                    "error": str(e),
                })

        _complete_success(session, async_task, results)
        return results

    except Exception as e:
        logger.error(f"批量处理开户请求失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"批量处理开户请求 ({len(request_ids)}个)",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()


# ========== 非活跃用户清理任务 ==========

@huey.task()
def cleanup_inactive_users(days_inactive: int = 30) -> dict:
    """清理非活跃用户（超过指定天数未登录）"""
    session = _get_sync_session()
    try:
        async_task = _create_async_task(
            session,
            name=f"清理非活跃用户 (超过{days_inactive}天未使用)",
        )

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_inactive)

        # 查找非活跃的云电脑用户
        inactive_users = session.query(CloudComputerUser).filter(
            CloudComputerUser.status == "active",
        ).all()

        cleaned_count = 0
        for cloud_user in inactive_users:
            # 检查用户是否有最近活动
            # 由于 CloudComputerUser 没有 last_login 字段，
            # 这里通过 RdpDomainRoute 的 last_activity_at 间接判断
            has_recent_activity = session.query(RdpDomainRoute).filter(
                RdpDomainRoute.assigned_to_id == cloud_user.owner_id,
                RdpDomainRoute.last_activity_at > cutoff_date,
            ).first() is not None

            if not has_recent_activity:
                try:
                    product = cloud_user.product
                    host = product.host
                    client = _get_host_client(host)
                    result = client.disabled_user(cloud_user.username)

                    if result.success:
                        cloud_user.status = "disabled"
                        cleaned_count += 1
                    else:
                        logger.warning(
                            f"无法禁用用户 {cloud_user.username}: {result.std_err}"
                        )
                except Exception as e:
                    logger.warning(f"禁用用户 {cloud_user.username} 失败: {e}")

        session.commit()

        _complete_success(session, async_task, {
            "cleaned_users": cleaned_count,
            "total_inactive": len(inactive_users),
        })

        return {
            "success": True,
            "cleaned_users": cleaned_count,
            "total_inactive": len(inactive_users),
        }

    except Exception as e:
        session.rollback()
        logger.error(f"清理非活跃用户失败: {e}", exc_info=True)
        try:
            async_task = session.query(AsyncTask).filter(
                AsyncTask.name == f"清理非活跃用户 (超过{days_inactive}天未使用)",
                AsyncTask.status == "running",
            ).first()
            if async_task:
                _complete_failure(session, async_task, str(e))
        except Exception:
            pass
        return {"success": False, "error": str(e)}
    finally:
        session.close()
