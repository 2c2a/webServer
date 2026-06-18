"""SQLAlchemy 2.0 异步模型包。

导入所有模型类以便 Alembic autogenerate 发现全部表。
所有模型继承 Base（声明式基类），需要时间戳的混入 TimestampMixin。
"""
from __future__ import annotations

from app.models.base import Base, TimestampMixin
from app.models.tenant import (
    SiteGroup,
    SiteGroupConfig,
    SiteGroupHostname,
    SystemConfig,
)
from app.models.user import (
    LoginLog,
    RegistrationLink,
    User,
    UserBan,
    UserBanHistory,
    UserEmail,
    UserGroup,
    UserProfile,
)
from app.models.host import (
    Host,
    HostGroup,
)
from app.models.operations import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    ProductAccessGrant,
    ProductGroup,
    ProductInvitationToken,
    PublicHostInfo,
    RdpDomainRoute,
    SystemTask,
)
from app.models.ticket import (
    Ticket,
    TicketActivity,
    TicketAttachment,
    TicketCategory,
    TicketComment,
)
from app.models.audit import (
    AuditLog,
    SecurityEvent,
    SensitiveOperation,
    SessionActivity,
)
from app.models.certificate import (
    CertificateAuthority,
    ClientCertificate,
    ServerCertificate,
)
from app.models.bootstrap import (
    ActiveSession,
    CertProvisionToken,
    InitialToken,
)
from app.models.theme import (
    PageContent,
    ThemeConfig,
)
from app.models.task import (
    AsyncTask,
    TaskProgress,
)
from app.models.plugin import (
    PluginConfiguration,
    PluginRecord,
)

__all__ = [
    # base
    "Base",
    "TimestampMixin",
    # tenant
    "SystemConfig",
    "SiteGroup",
    "SiteGroupConfig",
    "SiteGroupHostname",
    # user
    "User",
    "UserEmail",
    "UserProfile",
    "UserBan",
    "UserBanHistory",
    "LoginLog",
    "RegistrationLink",
    "UserGroup",
    # host
    "Host",
    "HostGroup",
    # operations
    "PublicHostInfo",
    "SystemTask",
    "ProductGroup",
    "Product",
    "AccountOpeningRequest",
    "CloudComputerUser",
    "RdpDomainRoute",
    "ProductInvitationToken",
    "ProductAccessGrant",
    # ticket
    "TicketCategory",
    "Ticket",
    "TicketComment",
    "TicketActivity",
    "TicketAttachment",
    # audit
    "AuditLog",
    "SensitiveOperation",
    "SecurityEvent",
    "SessionActivity",
    # certificate
    "CertificateAuthority",
    "ServerCertificate",
    "ClientCertificate",
    # bootstrap
    "InitialToken",
    "ActiveSession",
    "CertProvisionToken",
    # theme
    "ThemeConfig",
    "PageContent",
    # task
    "AsyncTask",
    "TaskProgress",
    # plugin
    "PluginRecord",
    "PluginConfiguration",
]
