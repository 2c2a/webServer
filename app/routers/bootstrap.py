"""
引导/配对端点路由

包含引导初始化、配对、会话创建、证书配置等
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.dependencies import DBSession, StaffUser
from app.models.bootstrap import ActiveSession, CertProvisionToken, InitialToken
from app.models.host import Host
from app.schemas.bootstrap import (
    BootstrapPairRequest,
    BootstrapSessionResponse,
    CertProvisionRequest,
    CertProvisionTokenResponse,
    InitialTokenResponse,
)
from app.schemas.common import APIResponse
from app.tasks.bootstrap import cert_provision_issue_certs, initialize_host_bootstrap

router = APIRouter()


@router.post(
    "/api/bootstrap/init",
    response_model=APIResponse[InitialTokenResponse],
    tags=["bootstrap"],
)
async def bootstrap_init(
    host_id: str,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """初始化引导（获取初始令牌）"""
    result = await db.execute(select(Host).where(Host.id == host_id))
    host = result.scalar_one_or_none()
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="主机不存在")

    token = InitialToken(
        token=str(uuid4()),
        host_id=host_id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        status="ISSUED",
    )
    db.add(token)
    await db.flush()

    # 异步初始化引导
    initialize_host_bootstrap(host_id, operator_id=user.id)

    return APIResponse(
        data=InitialTokenResponse.model_validate(token),
        message="引导初始化成功",
    )


@router.post(
    "/api/bootstrap/pair",
    response_model=APIResponse[InitialTokenResponse],
    tags=["bootstrap"],
)
async def bootstrap_pair(
    body: BootstrapPairRequest,
    db: DBSession,
):
    """使用配对码配对"""
    result = await db.execute(
        select(InitialToken).where(InitialToken.token == body.token)
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="令牌不存在")

    if token.status != "ISSUED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="令牌状态不允许配对",
        )

    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="令牌已过期",
        )

    # 验证配对码
    if token.pairing_code != body.pairing_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="配对码错误",
        )

    token.is_paired = True
    token.paired_at = datetime.now(timezone.utc)
    token.status = "PAIRED"
    await db.flush()

    return APIResponse(
        data=InitialTokenResponse.model_validate(token),
        message="配对成功",
    )


@router.post(
    "/api/bootstrap/session",
    response_model=APIResponse[BootstrapSessionResponse],
    tags=["bootstrap"],
)
async def bootstrap_create_session(
    token: str,
    db: DBSession,
):
    """创建活动会话"""
    result = await db.execute(
        select(InitialToken).where(InitialToken.token == token)
    )
    initial_token = result.scalar_one_or_none()
    if not initial_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="令牌不存在")

    if not initial_token.is_paired:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="令牌未配对",
        )

    session_token = str(uuid4())
    session = ActiveSession(
        session_token=session_token,
        host_id=initial_token.host_id,
        bound_ip="",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db.add(session)
    await db.flush()

    return APIResponse(
        data=BootstrapSessionResponse(
            session_token=session_token,
            expires_at=session.expires_at,
        ),
        message="会话创建成功",
    )


@router.post(
    "/api/bootstrap/cert-provision",
    response_model=APIResponse[CertProvisionTokenResponse],
    tags=["bootstrap"],
)
async def bootstrap_cert_provision(
    body: CertProvisionRequest,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """启动证书配置"""
    provision_token = CertProvisionToken(
        token=str(uuid4()),
        host_id=None,
        server_host=body.server_host,
        hostname=body.hostname,
        ip_address=body.ip_address,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        status="ISSUED",
        created_by_id=user.id,
    )
    db.add(provision_token)
    await db.flush()

    return APIResponse(
        data=CertProvisionTokenResponse.model_validate(provision_token),
        message="证书配置令牌已创建",
    )


@router.post(
    "/api/bootstrap/cert-provision/{token}/upload-hostname",
    response_model=APIResponse[CertProvisionTokenResponse],
    tags=["bootstrap"],
)
async def bootstrap_cert_upload_hostname(
    token: str,
    hostname: str,
    ip_address: str = "",
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """上传主机名（证书配置流程）"""
    result = await db.execute(
        select(CertProvisionToken).where(CertProvisionToken.token == token)
    )
    provision_token = result.scalar_one_or_none()
    if not provision_token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="令牌不存在")

    if provision_token.status != "ISSUED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="令牌状态不允许上传主机名",
        )

    provision_token.hostname = hostname
    provision_token.ip_address = ip_address
    provision_token.status = "HOSTNAME_UPLOADED"
    await db.flush()

    # 异步签发证书
    cert_provision_issue_certs(token)

    return APIResponse(
        data=CertProvisionTokenResponse.model_validate(provision_token),
        message="主机名已上传，证书签发任务已提交",
    )
