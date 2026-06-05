"""
本地 Windows 服务器客户端

直接在本地执行 PowerShell 命令，用于管理本机用户。
同步实现，适用于 Huey 任务和 FastAPI run_in_executor。
"""
import logging
import os
import re
import secrets
import string
import subprocess
from dataclasses import dataclass
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{1,150}$')
GROUPNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\s]{1,256}$')
MAX_STRING_LENGTH = 4096


class CommandInjectionError(Exception):
    pass


def _validate_username(username: str) -> str:
    if not username:
        raise CommandInjectionError("用户名不能为空")
    if len(username) > 150:
        raise CommandInjectionError("用户名长度不能超过150个字符")
    if not USERNAME_PATTERN.match(username):
        raise CommandInjectionError("用户名格式无效: 只允许字母、数字和下划线")
    return username


def _validate_groupname(group: str) -> str:
    if not group:
        raise CommandInjectionError("组名不能为空")
    if len(group) > 256:
        raise CommandInjectionError("组名长度不能超过256个字符")
    if not GROUPNAME_PATTERN.match(group):
        raise CommandInjectionError("组名格式无效: 只允许字母、数字、下划线、连字符和空格")
    return group


def _validate_string_length(s: str, max_length: int = MAX_STRING_LENGTH, field_name: str = "输入") -> str:
    if s and len(s) > max_length:
        raise CommandInjectionError(f"{field_name}长度不能超过{max_length}个字符")
    return s


def _escape_ps_string(s: str) -> str:
    """转义 PowerShell 双引号字符串中的特殊字符"""
    if not s:
        return s
    if len(s) > MAX_STRING_LENGTH:
        raise CommandInjectionError(f"字符串长度超过最大限制 {MAX_STRING_LENGTH}")
    return (
        s.replace('\x00', '')
        .replace('`', '``')
        .replace('"', '`"')
        .replace('$', '`$')
        .replace('\n', '`n')
        .replace('\r', '`r')
    )


@dataclass
class LocalWinServerResult:
    """本地命令执行结果"""
    status_code: int
    std_out: str
    std_err: str

    @property
    def success(self) -> bool:
        return self.status_code == 0


class LocalWinServerClient:
    """
    本地 Windows 服务器客户端

    通过 subprocess 调用 PowerShell 执行本地管理操作，
    绕过网络连接限制。
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        settings = get_settings()
        self.username = username or ""
        self.password = password or ""
        self.timeout = timeout or settings.winrm_timeout
        self.max_retries = max_retries or settings.winrm_max_retries

        logger.info(
            "初始化本地WinServer客户端: 超时=%d秒, 最大重试=%d次",
            self.timeout, self.max_retries,
        )

    def execute_command(
        self,
        command: str,
        arguments: Optional[list] = None,
    ) -> LocalWinServerResult:
        """执行本地命令（通过 PowerShell）"""
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info("DEMO模式: 模拟执行本地命令: %s", command)
            return LocalWinServerResult(status_code=0, std_out="Command executed successfully in demo mode", std_err="")

        logger.info("执行本地命令: %s", command)

        try:
            if arguments:
                cmd_parts = [command] + [str(arg) for arg in arguments]
                ps_command = ' '.join(cmd_parts)
            else:
                ps_command = command

            full_command = ['powershell.exe', '-Command', ps_command]
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            local_result = LocalWinServerResult(
                status_code=result.returncode,
                std_out=result.stdout,
                std_err=result.stderr,
            )

            if local_result.success:
                logger.info("本地命令执行成功: %s", command)
            else:
                logger.warning(
                    "本地命令执行返回非零状态码: %s, 状态码=%d",
                    command, result.returncode,
                )

            return local_result
        except subprocess.TimeoutExpired:
            logger.error("本地命令执行超时: %s", command)
            return LocalWinServerResult(status_code=-1, std_out="", std_err=f"命令执行超时 ({self.timeout}秒)")
        except Exception as e:
            logger.error("本地命令执行失败: %s, 错误: %s", command, str(e))
            return LocalWinServerResult(status_code=-1, std_out="", std_err=str(e))

    def execute_powershell(
        self,
        script: str,
        arguments: Optional[dict] = None,
    ) -> LocalWinServerResult:
        """执行本地 PowerShell 脚本"""
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info("DEMO模式: 模拟执行本地PowerShell脚本")
            return LocalWinServerResult(
                status_code=0,
                std_out="PowerShell script executed successfully in demo mode",
                std_err="",
            )

        logger.info("执行本地PowerShell脚本")

        try:
            full_command = ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-Command', script]
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            local_result = LocalWinServerResult(
                status_code=result.returncode,
                std_out=result.stdout,
                std_err=result.stderr,
            )

            if local_result.success:
                logger.info("本地PowerShell脚本执行成功")
            else:
                logger.warning(
                    "本地PowerShell脚本执行返回非零状态码: 状态码=%d",
                    result.returncode,
                )

            return local_result
        except subprocess.TimeoutExpired:
            logger.error("本地PowerShell脚本执行超时")
            return LocalWinServerResult(
                status_code=-1,
                std_out="",
                std_err=f"PowerShell脚本执行超时 ({self.timeout}秒)",
            )
        except Exception as e:
            logger.error("本地PowerShell脚本执行失败: %s", str(e))
            return LocalWinServerResult(status_code=-1, std_out="", std_err=str(e))

    def create_user(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> LocalWinServerResult:
        """创建本地用户"""
        try:
            _validate_username(username)
            _validate_string_length(password, field_name="密码")
            if description:
                _validate_string_length(description, field_name="描述")
            if group:
                _validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return LocalWinServerResult(1, '', str(e))

        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        safe_desc = _escape_ps_string(description or '')

        script = f'''
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
New-LocalUser -Name "{safe_user}" -Password $pw -Description "{safe_desc}" -ErrorAction Stop
Add-LocalGroupMember -Group "Users" -Member "{safe_user}" -ErrorAction Stop
'''
        if group:
            safe_group = _escape_ps_string(group)
            script += f'Add-LocalGroupMember -Group "{safe_group}" -Member "{safe_user}" -ErrorAction Stop\n'

        logger.info("创建本地用户: %s", username)
        result = self.execute_powershell(script)
        self.add_to_remote_users(username)
        return result

    def delete_user(self, username: str) -> LocalWinServerResult:
        """删除本地用户"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Remove-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("删除本地用户: %s", username)
        return self.execute_powershell(script)

    def enable_user(self, username: str) -> LocalWinServerResult:
        """启用本地用户"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Enable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("启用本地用户: %s", username)
        return self.execute_powershell(script)

    def disabled_user(self, username: str) -> LocalWinServerResult:
        """禁用本地用户"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Disable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("禁用本地用户: %s", username)
        return self.execute_powershell(script)

    def reset_password(self, username: str, password: str) -> LocalWinServerResult:
        """重置本地用户密码"""
        try:
            _validate_username(username)
            _validate_string_length(password, 256, "密码")
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        script = f'''
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
Set-LocalUser -Name "{safe_user}" -Password $pw
'''
        result = self.execute_powershell(script)
        if result.success:
            self.add_to_remote_users(username)
        return result

    def op_user(self, username: str) -> LocalWinServerResult:
        """将用户添加到 Administrators 组"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'net localgroup Administrators "{safe_user}" /add'
        logger.info("提升本地用户为管理员: %s", username)
        return self.execute_powershell(script)

    def deop_user(self, username: str) -> LocalWinServerResult:
        """从 Administrators 组移除用户"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'net localgroup Administrators "{safe_user}" /delete'
        logger.info("取消本地用户管理员: %s", username)
        return self.execute_powershell(script)

    def add_to_remote_users(self, username: str) -> LocalWinServerResult:
        """将用户添加到 Remote Desktop Users 组"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = (
            f'Add-LocalGroupMember -Group "Remote Desktop Users" '
            f'-Member "{safe_user}" -ErrorAction SilentlyContinue'
        )
        return self.execute_powershell(script)

    def check_user_exists(self, username: str) -> LocalWinServerResult:
        """检查本地用户是否存在"""
        try:
            _validate_username(username)
        except CommandInjectionError as e:
            return LocalWinServerResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'$u = Get-LocalUser -Name "{safe_user}" -ErrorAction Stop; $true'
        return self.execute_powershell(script)

    def generate_strong_password(self, length: Optional[int] = None) -> str:
        """根据密码策略生成强密码"""
        policy = self.get_password_policy()
        actual_length = length or max(policy["minimum_length"], 12)

        if policy["complexity_required"]:
            uppercase = secrets.choice(string.ascii_uppercase)
            lowercase = secrets.choice(string.ascii_lowercase)
            digit = secrets.choice(string.digits)
            special_char = secrets.choice("!@#$%^&*()_+-=[]{}|;:,.<>?")

            remaining_length = max(0, actual_length - 4)
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
            rest = "".join(secrets.choice(alphabet) for _ in range(remaining_length))

            password_chars = list(uppercase + lowercase + digit + special_char + rest)
            secrets.SystemRandom().shuffle(password_chars)
            password = "".join(password_chars)
        else:
            alphabet = string.ascii_letters + string.digits
            password = "".join(secrets.choice(alphabet) for _ in range(actual_length))

        logger.info("生成本地强密码完成，长度: %d", len(password))
        return password

    def get_password_policy(self) -> dict:
        """获取本地密码策略"""
        try:
            script = (
                'secedit /export /cfg "$env:TEMP\\secpol.cfg" | Out-Null\n'
                'Get-Content "$env:TEMP\\secpol.cfg" | Where-Object '
                '{ $_ -match \'^(MinimumPasswordLength|PasswordComplexity'
                '|PasswordHistorySize|MaximumPasswordAge'
                '|MinimumPasswordAge)\\\\s*=\' }\n'
                'Remove-Item "$env:TEMP\\secpol.cfg" -ErrorAction SilentlyContinue'
            )
            result = self.execute_powershell(script)

            policy = {}
            if result.success:
                lines = result.std_out.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("MinimumPasswordLength"):
                        try:
                            policy["minimum_length"] = int(line.split("=")[1].strip())
                        except (ValueError, IndexError):
                            policy["minimum_length"] = 8
                    elif line.startswith("PasswordComplexity"):
                        try:
                            policy["complexity_required"] = bool(int(line.split("=")[1].strip()))
                        except (ValueError, IndexError):
                            policy["complexity_required"] = True
                    elif line.startswith("PasswordHistorySize"):
                        try:
                            policy["history_size"] = int(line.split("=")[1].strip())
                        except (ValueError, IndexError):
                            policy["history_size"] = 0
                    elif line.startswith("MaximumPasswordAge"):
                        try:
                            policy["max_age_days"] = int(line.split("=")[1].strip())
                        except (ValueError, IndexError):
                            policy["max_age_days"] = 0
                    elif line.startswith("MinimumPasswordAge"):
                        try:
                            policy["min_age_days"] = int(line.split("=")[1].strip())
                        except (ValueError, IndexError):
                            policy["min_age_days"] = 0

            if "minimum_length" not in policy:
                policy["minimum_length"] = 8
            if "complexity_required" not in policy:
                policy["complexity_required"] = True

            logger.info("获取本地密码策略成功: %s", policy)
            return policy
        except Exception as e:
            logger.error("获取本地密码策略失败: %s", str(e))
            return {
                "minimum_length": 8,
                "complexity_required": True,
                "history_size": 0,
                "max_age_days": 42,
                "min_age_days": 1,
            }
