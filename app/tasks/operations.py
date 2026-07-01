"""开户/云电脑相关异步任务。"""
from __future__ import annotations

from app.tasks.huey_app import huey


@huey.task()
async def process_account_opening(request_id: int) -> dict:
    """异步处理开户申请：在远程主机创建用户、配置磁盘配额等。

    前端提交开户后立即返回，后台执行 WinRM 操作。
    """
    from app.core.db import AsyncSessionLocal
    from app.core.logging import get_logger
    from app.models.operations import AccountOpeningRequest, CloudComputerUser
    from app.models.host import Host
    from app.security.field_cipher import decrypt_field, encrypt_field
    from app.winrm import AsyncWinRMClient
    from sqlalchemy import select

    log = get_logger(__name__)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AccountOpeningRequest).where(AccountOpeningRequest.id == request_id)
        )
        req = result.scalar_one_or_none()
        if req is None:
            return {"success": False, "error": "开户申请不存在"}

        # 加载关联主机
        host_result = await db.execute(
            select(Host).join(
                AccountOpeningRequest, AccountOpeningRequest.target_product_id
            )
        )

        try:
            # 查找产品对应主机
            from app.models.operations import Product

            prod_result = await db.execute(
                select(Product).where(Product.id == req.target_product_id)
            )
            product = prod_result.scalar_one_or_none()
            if product is None:
                return {"success": False, "error": "产品不存在"}

            from sqlalchemy.orm import selectinload

            host_result = await db.execute(
                select(Host)
                .options(selectinload(Host.site_group))
                .where(Host.id == product.host_id)
            )
            host = host_result.scalar_one_or_none()
            if host is None:
                return {"success": False, "error": "主机不存在"}

            site_is_demo = host.site_group.is_demo if host.site_group else False
            client = await AsyncWinRMClient.from_host_config(host, site_is_demo=site_is_demo)
            # 生成强密码
            password = client.generate_strong_password()
            # 创建远程用户
            create_res = await client.create_user(
                username=req.username,
                password=password,
                description=req.user_description or "",
            )
            if not create_res.success:
                await client.close()
                return {"success": False, "error": create_res.std_err}

            # 加入 Remote Desktop Users
            await client.add_to_remote_users(req.username)
            await client.close()

            # 创建 CloudComputerUser 记录（密码加密存储，阅后即焚）
            ccu = CloudComputerUser(
                username=req.username,
                fullname=req.user_fullname,
                email=req.user_email,
                description=req.user_description,
                product_id=product.id,
                status="active",
                created_from_request_id=req.id,
                owner_id=req.applicant_id,
                initial_password_cipher=encrypt_field(password, "cloud_computer_user.initial_password"),
            )
            db.add(ccu)
            req.status = "completed"
            req.cloud_user_id = req.username
            await db.commit()

            log.info("account_opening_done", request_id=request_id, username=req.username)
            return {"success": True, "username": req.username}
        except Exception as e:  # noqa: BLE001
            log.exception("account_opening_failed", request_id=request_id)
            req.status = "failed"
            req.result_message = str(e)
            await db.commit()
            return {"success": False, "error": str(e)}
