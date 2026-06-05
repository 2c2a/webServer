"""
SQLAlchemy 模型包

导出所有模型类和关联表
"""

# 用户管理
from app.models.user import (
    Group,
    GroupProfile,
    LoginLog,
    RegistrationLink,
    User,
    UserProfile,
    site_group_admins,
    user_groups,
    user_site_groups,
)

# 主机管理
from app.models.host import (
    Host,
    HostGroup,
    host_administrators,
    hostgroup_hosts,
    hostgroup_providers,
    host_providers,
)

# 产品与运营
from app.models.product import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    ProductAccessGrant,
    ProductGroup,
    ProductInvitationToken,
    PublicHostInfo,
    RdpDomainRoute,
    SystemTask,
    productgroup_auto_assign_providers,
)

# 仪表盘与系统配置
from app.models.dashboard import (
    DashboardWidget,
    SiteGroup,
    SiteGroupHostname,
    SystemConfig,
)

# 证书管理
from app.models.certificate import (
    CertificateAuthority,
    ClientCertificate,
    ServerCertificate,
)

# 审计日志
from app.models.audit import (
    AuditLog,
    SecurityEvent,
    SensitiveOperation,
    SessionActivity,
)

# 异步任务
from app.models.task import (
    AsyncTask,
    TaskProgress,
)

# 主题系统
from app.models.theme import (
    PageContent,
    ThemeConfig,
    WidgetLayout,
)

# 工单系统
from app.models.ticket import (
    Ticket,
    TicketActivity,
    TicketAttachment,
    TicketCategory,
    TicketComment,
)

# 引导与令牌
from app.models.bootstrap import (
    ActiveSession,
    CertProvisionToken,
    InitialToken,
)

# 插件
from app.models.plugin import (
    PluginConfiguration,
    PluginRecord,
)

__all__ = [
    # 用户管理
    "Group",
    "GroupProfile",
    "LoginLog",
    "RegistrationLink",
    "User",
    "UserProfile",
    "site_group_admins",
    "user_groups",
    "user_site_groups",
    # 主机管理
    "Host",
    "HostGroup",
    "host_administrators",
    "hostgroup_hosts",
    "hostgroup_providers",
    "host_providers",
    # 产品与运营
    "AccountOpeningRequest",
    "CloudComputerUser",
    "Product",
    "ProductAccessGrant",
    "ProductGroup",
    "ProductInvitationToken",
    "PublicHostInfo",
    "RdpDomainRoute",
    "SystemTask",
    "productgroup_auto_assign_providers",
    # 仪表盘与系统配置
    "DashboardWidget",
    "SiteGroup",
    "SiteGroupHostname",
    "SystemConfig",
    # 证书管理
    "CertificateAuthority",
    "ClientCertificate",
    "ServerCertificate",
    # 审计日志
    "AuditLog",
    "SecurityEvent",
    "SensitiveOperation",
    "SessionActivity",
    # 异步任务
    "AsyncTask",
    "TaskProgress",
    # 主题系统
    "PageContent",
    "ThemeConfig",
    "WidgetLayout",
    # 工单系统
    "Ticket",
    "TicketActivity",
    "TicketAttachment",
    "TicketCategory",
    "TicketComment",
    # 引导与令牌
    "ActiveSession",
    "CertProvisionToken",
    "InitialToken",
    # 插件
    "PluginConfiguration",
    "PluginRecord",
]
