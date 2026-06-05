"""
Pydantic Schema 模式包

导出通用模式供 FastAPI 路由使用
"""
from app.schemas.common import APIResponse, PaginatedResponse, PaginationParams
from app.schemas.user import (
    LoginAPIResponse,
    LoginRequest,
    LoginResponse,
    PasswordChange,
    PasswordReset,
    TokenRefresh,
    UserAPIResponse,
    UserBriefResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.schemas.host import (
    HostBriefResponse,
    HostCreate,
    HostGroupCreate,
    HostGroupResponse,
    HostGroupUpdate,
    HostResponse,
    HostUpdate,
)
from app.schemas.product import (
    AccountOpeningRequestCreate,
    AccountOpeningRequestResponse,
    AccountOpeningRequestUpdate,
    CloudComputerUserCreate,
    CloudComputerUserResponse,
    CloudComputerUserUpdate,
    ProductBriefForCloudUser,
    ProductCreate,
    ProductGroupBriefResponse,
    ProductGroupCreate,
    ProductGroupResponse,
    ProductGroupUpdate,
    ProductResponse,
    ProductUpdate,
)
from app.schemas.dashboard import (
    DashboardWidgetCreate,
    DashboardWidgetResponse,
    DashboardWidgetUpdate,
    SiteGroupCreate,
    SiteGroupResponse,
    SiteGroupUpdate,
    SystemConfigResponse,
    SystemConfigUpdate,
)
from app.schemas.certificate import (
    CertificateAuthorityBriefResponse,
    CertificateAuthorityCreate,
    CertificateAuthorityResponse,
    CertificateAuthorityUpdate,
    ClientCertificateCreate,
    ClientCertificateResponse,
    ClientCertificateUpdate,
    ServerCertificateCreate,
    ServerCertificateResponse,
)
from app.schemas.ticket import (
    TicketCategoryBriefResponse,
    TicketCategoryCreate,
    TicketCategoryResponse,
    TicketCategoryUpdate,
    TicketCommentCreate,
    TicketCommentResponse,
    TicketCreate,
    TicketResponse,
    TicketUpdate,
)
from app.schemas.task import AsyncTaskResponse, TaskProgressResponse
from app.schemas.audit import (
    AuditLogQuery,
    AuditLogResponse,
    SecurityEventResponse,
    SensitiveOperationResponse,
    SessionActivityResponse,
)
from app.schemas.theme import (
    PageContentCreate,
    PageContentResponse,
    PageContentUpdate,
    ThemeConfigResponse,
    ThemeConfigUpdate,
    WidgetLayoutCreate,
    WidgetLayoutResponse,
    WidgetLayoutUpdate,
)
from app.schemas.bootstrap import (
    ActiveSessionResponse,
    BootstrapPairRequest,
    BootstrapSessionResponse,
    CertProvisionRequest,
    CertProvisionTokenResponse,
    InitialTokenResponse,
)

__all__ = [
    # common
    "APIResponse",
    "PaginatedResponse",
    "PaginationParams",
    # user
    "UserCreate",
    "UserUpdate",
    "UserResponse",
    "UserBriefResponse",
    "LoginRequest",
    "LoginResponse",
    "LoginAPIResponse",
    "TokenRefresh",
    "PasswordChange",
    "PasswordReset",
    "UserAPIResponse",
    # host
    "HostCreate",
    "HostUpdate",
    "HostResponse",
    "HostBriefResponse",
    "HostGroupCreate",
    "HostGroupUpdate",
    "HostGroupResponse",
    # product
    "ProductGroupCreate",
    "ProductGroupUpdate",
    "ProductGroupBriefResponse",
    "ProductGroupResponse",
    "ProductCreate",
    "ProductUpdate",
    "ProductResponse",
    "ProductBriefForCloudUser",
    "AccountOpeningRequestCreate",
    "AccountOpeningRequestUpdate",
    "AccountOpeningRequestResponse",
    "CloudComputerUserCreate",
    "CloudComputerUserUpdate",
    "CloudComputerUserResponse",
    # dashboard
    "SystemConfigUpdate",
    "SystemConfigResponse",
    "SiteGroupCreate",
    "SiteGroupUpdate",
    "SiteGroupResponse",
    "DashboardWidgetCreate",
    "DashboardWidgetUpdate",
    "DashboardWidgetResponse",
    # certificate
    "CertificateAuthorityCreate",
    "CertificateAuthorityUpdate",
    "CertificateAuthorityResponse",
    "CertificateAuthorityBriefResponse",
    "ServerCertificateCreate",
    "ServerCertificateResponse",
    "ClientCertificateCreate",
    "ClientCertificateUpdate",
    "ClientCertificateResponse",
    # ticket
    "TicketCategoryCreate",
    "TicketCategoryUpdate",
    "TicketCategoryResponse",
    "TicketCategoryBriefResponse",
    "TicketCreate",
    "TicketUpdate",
    "TicketResponse",
    "TicketCommentCreate",
    "TicketCommentResponse",
    # task
    "AsyncTaskResponse",
    "TaskProgressResponse",
    # audit
    "AuditLogResponse",
    "AuditLogQuery",
    "SensitiveOperationResponse",
    "SecurityEventResponse",
    "SessionActivityResponse",
    # theme
    "ThemeConfigUpdate",
    "ThemeConfigResponse",
    "PageContentCreate",
    "PageContentUpdate",
    "PageContentResponse",
    "WidgetLayoutCreate",
    "WidgetLayoutUpdate",
    "WidgetLayoutResponse",
    # bootstrap
    "BootstrapPairRequest",
    "BootstrapSessionResponse",
    "InitialTokenResponse",
    "ActiveSessionResponse",
    "CertProvisionRequest",
    "CertProvisionTokenResponse",
]
