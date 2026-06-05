"""
证书管理路由

包含证书颁发机构、服务器证书、客户端证书管理
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select

from app.dependencies import DBSession, PaginationParams, StaffUser
from app.models.certificate import CertificateAuthority, ClientCertificate, ServerCertificate
from app.schemas.certificate import (
    CertificateAuthorityCreate,
    CertificateAuthorityResponse,
    ClientCertificateResponse,
    ServerCertificateResponse,
)
from app.schemas.common import APIResponse, PaginatedResponse

router = APIRouter()

# ========== 证书颁发机构 API ==========


@router.get(
    "/api/certificates/authorities",
    response_model=APIResponse[PaginatedResponse[CertificateAuthorityResponse]],
    tags=["certificates"],
)
async def list_certificate_authorities(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出证书颁发机构"""
    count_stmt = select(func.count()).select_from(CertificateAuthority)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(CertificateAuthority)
        .order_by(CertificateAuthority.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    authorities = result.scalars().all()

    items = [CertificateAuthorityResponse.model_validate(a) for a in authorities]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


@router.post(
    "/api/certificates/authorities",
    response_model=APIResponse[CertificateAuthorityResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["certificates"],
)
async def create_certificate_authority(
    body: CertificateAuthorityCreate,
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """创建证书颁发机构"""
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from cryptography.hazmat.primitives import serialization

    from utils.cert_service import generate_ca
    from utils.cert_storage import generate_ca_paths, save_ca_files

    # 生成 CA 密钥对
    ca_key, ca_cert = generate_ca()
    ca_key_pem = ca_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ca_cert_pem = ca_cert.public_bytes(serialization.Encoding.PEM)

    # 保存 CA 文件
    ca_root, ca_sub = generate_ca_paths()
    save_ca_files(ca_root, ca_sub, ca_key_pem, ca_cert_pem)

    authority = CertificateAuthority(
        id=str(uuid4()),
        name=body.name,
        cert_root=ca_root,
        cert_sub=ca_sub,
        description=body.description,
        is_active=True,
        expires_at=datetime.now(timezone.utc) + timedelta(days=3650),
    )
    db.add(authority)
    await db.flush()
    return APIResponse(
        data=CertificateAuthorityResponse.model_validate(authority),
        message="证书颁发机构创建成功",
    )


# ========== 服务器证书 API ==========


@router.get(
    "/api/certificates/server",
    response_model=APIResponse[PaginatedResponse[ServerCertificateResponse]],
    tags=["certificates"],
)
async def list_server_certificates(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出服务器证书"""
    count_stmt = select(func.count()).select_from(ServerCertificate)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(ServerCertificate)
        .order_by(ServerCertificate.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    certs = result.scalars().all()

    items = [ServerCertificateResponse.model_validate(c) for c in certs]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )


# ========== 客户端证书 API ==========


@router.get(
    "/api/certificates/client",
    response_model=APIResponse[PaginatedResponse[ClientCertificateResponse]],
    tags=["certificates"],
)
async def list_client_certificates(
    pagination: PaginationParams = Depends(),
    db: DBSession = ...,
    user: StaffUser = ...,
):
    """列出客户端证书"""
    count_stmt = select(func.count()).select_from(ClientCertificate)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(ClientCertificate)
        .order_by(ClientCertificate.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.execute(stmt)
    certs = result.scalars().all()

    items = [ClientCertificateResponse.model_validate(c) for c in certs]
    return APIResponse(
        data=PaginatedResponse(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )
    )
