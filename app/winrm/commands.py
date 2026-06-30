"""PowerShell 命令模板常量与构造函数。

所有模板中需要注入的参数，在调用方必须先经过 :func:`escape_ps_string` 转义，
再通过 ``str.format`` 注入，从而避免 PowerShell 命令注入风险。

注意：模板里出现的 ``{{`` / ``}}`` 是 ``str.format`` 的字面花括号转义，
对应 PowerShell 脚本中的单个 ``{`` / ``}``。
"""
from __future__ import annotations

import re

# 用户名白名单：字母、数字、点、下划线、连字符，长度 1-20
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,20}$")
# 组名白名单：相对宽松，允许字母、数字、点、下划线、连字符、空格、中英文括号及中文
GROUPNAME_PATTERN = re.compile(r"^[A-Za-z0-9._\-\s（）()\u4e00-\u9fa5]{1,64}$")

# 字符串最大长度，防止超长输入造成缓冲或日志膨胀
MAX_STRING_LENGTH = 4096


def validate_username(name: str) -> str:
    """校验用户名，符合白名单则原样返回，否则抛 ``ValueError``。"""
    if not name:
        raise ValueError("用户名不能为空")
    if len(name) > 20:
        raise ValueError("用户名长度不能超过 20 个字符")
    if not USERNAME_PATTERN.match(name):
        raise ValueError("用户名格式无效: 只允许字母、数字、点、下划线和连字符")
    return name


def validate_groupname(name: str) -> str:
    """校验组名，相对宽松（允许中文及中英文括号等），失败抛 ``ValueError``。"""
    if not name:
        raise ValueError("组名不能为空")
    if len(name) > 64:
        raise ValueError("组名长度不能超过 64 个字符")
    if not GROUPNAME_PATTERN.match(name):
        raise ValueError("组名格式无效: 含非法字符")
    return name


def escape_ps_string(s: str) -> str:
    """转义 PowerShell 双引号字符串中的特殊字符。

    转义字符为反引号 (````)，需转义的目标字符：
    - 反引号 `` ` ``
    - 双引号 `` "``
    - 美元符 `` $``
    - 换行 ``\\n`` / 回车 ``\\r``

    超长字符串抛 ``ValueError``，防止注入超长 payload。
    """
    if not s:
        return s
    if len(s) > MAX_STRING_LENGTH:
        raise ValueError(f"字符串长度超过最大限制 {MAX_STRING_LENGTH}")
    return (
        s.replace("\x00", "")  # 去除 NUL，避免截断绕过
        .replace("`", "``")
        .replace('"', '`"')
        .replace("$", "`$")
        .replace("\n", "`n")
        .replace("\r", "`r")
    )


# ---------------------------------------------------------------------------
# PowerShell 脚本模板
#
# 约定：占位符 {username} / {password} / {description} / {group} / {extra_group}
# 在调用方注入前，必须先经过 escape_ps_string 转义。
# ---------------------------------------------------------------------------

# 创建本地用户（不强制首登改密）
CREATE_USER_PS = """\
$ErrorActionPreference = 'Stop'
$pw = ConvertTo-SecureString "{password}" -AsPlainText -Force
New-LocalUser -Name "{username}" -Password $pw -Description "{description}" -ErrorAction Stop
net user "{username}" /logonpasswordchg:NO
Add-LocalGroupMember -Group "Users" -Member "{username}" -ErrorAction Stop
{extra_group}
"""

# 创建本地用户（首登强制修改密码）
CREATE_USER_RESET_PS = """\
$ErrorActionPreference = 'Stop'
$pw = ConvertTo-SecureString "{password}" -AsPlainText -Force
New-LocalUser -Name "{username}" -Password $pw -Description "{description}" -ErrorAction Stop
net user "{username}" /logonpasswordchg:YES
Add-LocalGroupMember -Group "Users" -Member "{username}" -ErrorAction Stop
{extra_group}
"""

# 删除用户
DELETE_USER_PS = 'Remove-LocalUser -Name "{username}" -ErrorAction Stop'

# 启用用户
ENABLE_USER_PS = 'Enable-LocalUser -Name "{username}" -ErrorAction Stop'

# 禁用用户
DISABLE_USER_PS = 'Disable-LocalUser -Name "{username}" -ErrorAction Stop'

# 获取单个用户信息（JSON）
GET_USER_INFO_PS = 'Get-LocalUser -Name "{username}" | ConvertTo-Json'

# 列出所有本地用户（JSON）
LIST_USERS_PS = "Get-LocalUser | ConvertTo-Json"

# 重置密码
RESET_PASSWORD_PS = """\
$ErrorActionPreference = 'Stop'
$pw = ConvertTo-SecureString "{password}" -AsPlainText -Force
Set-LocalUser -Name "{username}" -Password $pw
net user "{username}" /logonpasswordchg:NO
"""

# 加入指定组（参数化 group 名）
ADD_TO_GROUP_PS = (
    'Add-LocalGroupMember -Group "{group}" -Member "{username}" '
    "-ErrorAction SilentlyContinue"
)

# 加入 Remote Desktop Users 组
ADD_TO_REMOTE_USERS_PS = (
    'Add-LocalGroupMember -Group "Remote Desktop Users" -Member "{username}" '
    "-ErrorAction SilentlyContinue"
)

# 授予管理员权限（加入 Administrators）
GRANT_ADMIN_PS = 'net localgroup Administrators "{username}" /add'

# 撤销管理员权限（移出 Administrators）
REVOKE_ADMIN_PS = 'net localgroup Administrators "{username}" /delete'

# 检查用户是否存在（存在则输出 True）
CHECK_USER_EXISTS_PS = (
    '$u = Get-LocalUser -Name "{username}" -ErrorAction Stop; $true'
)

# 获取密码策略：通过 secedit 导出并解析关键字段
# 注意：脚本内 Where-Object 的花括号是 PowerShell 语法，无需 format 注入参数，
# 因此保持单花括号（本模板不含占位符，不经过 str.format）。
GET_PASSWORD_POLICY_PS = """\
secedit /export /cfg "$env:TEMP\\secpol.cfg" | Out-Null
Get-Content "$env:TEMP\\secpol.cfg" | Where-Object { $_ -match '^(MinimumPasswordLength|PasswordComplexity|PasswordHistorySize|MaximumPasswordAge|MinimumPasswordAge)\\s*=' }
Remove-Item "$env:TEMP\\secpol.cfg" -ErrorAction SilentlyContinue
"""
