"""
WinRM 客户端服务

远程管理 Windows 主机，支持 NTLM 和证书认证。
同步实现，适用于 Huey 任务和 FastAPI run_in_executor。
"""
import logging
import os
import re
import secrets
import socket
import string
import time
from dataclasses import dataclass
from typing import Optional

from winrm import Session

from app.config import get_settings

logger = logging.getLogger(__name__)

USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{1,150}$')
GROUPNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\s]{1,256}$')
MAX_STRING_LENGTH = 4096


class CommandInjectionError(Exception):
    pass


def validate_username(username: str) -> str:
    if not username:
        raise CommandInjectionError("用户名不能为空")
    if len(username) > 150:
        raise CommandInjectionError("用户名长度不能超过150个字符")
    if not USERNAME_PATTERN.match(username):
        raise CommandInjectionError("用户名格式无效: 只允许字母、数字和下划线")
    return username


def validate_groupname(group: str) -> str:
    if not group:
        raise CommandInjectionError("组名不能为空")
    if len(group) > 256:
        raise CommandInjectionError("组名长度不能超过256个字符")
    if not GROUPNAME_PATTERN.match(group):
        raise CommandInjectionError("组名格式无效: 只允许字母、数字、下划线、连字符和空格")
    return group


def validate_string_length(s: str, max_length: int = MAX_STRING_LENGTH, field_name: str = "输入") -> str:
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


def _escape_for_here_string(s: str) -> str:
    """转义 PowerShell here-string 内容"""
    if not s:
        return s
    s = s.replace('\x00', '')
    if '@"' in s or '"@' in s:
        raise CommandInjectionError("内容包含非法的 here-string 分隔符")
    return s


@dataclass
class WinrmResult:
    """WinRM 命令执行结果"""
    status_code: int
    std_out: str
    std_err: str

    @property
    def success(self) -> bool:
        return self.status_code == 0


class WinrmClient:
    """WinRM 客户端 - 远程管理 Windows 主机"""

    def __init__(
        self,
        hostname: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 5985,
        use_ssl: bool = False,
        auth_method: str = 'ntlm',
        cert_pem_path: Optional[str] = None,
        cert_key_path: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        server_cert_validation: str = 'validate',
        ca_trust_path: Optional[str] = None,
        client_cert_pem: Optional[str] = None,
        client_cert_key: Optional[str] = None,
    ):
        settings = get_settings()

        if auth_method == 'certificate':
            if not cert_pem_path and client_cert_pem:
                cert_pem_path = client_cert_pem
            if not cert_key_path and client_cert_key:
                cert_key_path = client_cert_key
            if not cert_pem_path or not cert_key_path:
                raise ValueError("证书认证方式必须提供证书和私钥路径")
            if not os.path.exists(cert_pem_path):
                raise ValueError(f"客户端证书文件不存在: {cert_pem_path}")
            if not os.path.exists(cert_key_path):
                raise ValueError(f"客户端私钥文件不存在: {cert_key_path}")
            self.auth_method = 'certificate'
            self.cert_pem_path = cert_pem_path
            self.cert_key_path = cert_key_path
            self.username = username or ''
            self.password = password or ''
        elif auth_method == 'ntlm':
            if not username:
                raise ValueError("NTLM认证方式必须提供用户名")
            if not password:
                raise ValueError("NTLM认证方式必须提供密码")
            self.auth_method = 'ntlm'
            self.username = username
            self.password = password
            self.cert_pem_path = ''
            self.cert_key_path = ''
        else:
            raise ValueError(f"不支持的认证方式: {auth_method}")

        # 解析 hostname:port 格式
        if ':' in hostname and not hostname.startswith('http'):
            parts = hostname.split(':', 1)
            if len(parts) == 2 and parts[1].isdigit():
                actual_hostname = parts[0]
                actual_port = int(parts[1])
                self.hostname = actual_hostname
                self.port = actual_port if port == 5985 else port
            else:
                self.hostname = hostname
                self.port = port
        else:
            self.hostname = hostname
            self.port = port

        self.use_ssl = use_ssl
        self.timeout = timeout or settings.winrm_timeout
        self.max_retries = max_retries or settings.winrm_max_retries
        self.server_cert_validation = server_cert_validation
        self.ca_trust_path = ca_trust_path

        if server_cert_validation == 'ignore':
            logger.warning(
                "WinRM连接到 %s 未启用服务器证书验证，存在中间人攻击风险",
                hostname,
            )

        if use_ssl and server_cert_validation == 'validate':
            if not ca_trust_path:
                logger.warning("SSL验证启用但未提供CA证书路径，将使用系统默认证书")
            elif not os.path.exists(ca_trust_path):
                logger.error("CA证书文件不存在: %s", ca_trust_path)
                raise ValueError(f"CA证书文件不存在: {ca_trust_path}")

        if self.auth_method == 'certificate':
            transport = 'certificate'
            if not self.use_ssl:
                self.use_ssl = True
            if self.port == 5985:
                self.port = 5986
        else:
            transport = 'ntlm'

        protocol = 'https' if self.use_ssl else 'http'
        self.endpoint = f'{protocol}://{self.hostname}:{self.port}/wsman'

        if not self._validate_hostname():
            raise ValueError(f"主机名无法解析: {self.hostname}")

        session_kwargs = dict(
            transport=transport,
            server_cert_validation=self.server_cert_validation,
            ca_trust_path=self.ca_trust_path or None,
            operation_timeout_sec=self.timeout,
            read_timeout_sec=self.timeout + 10,
        )
        if self.auth_method == 'certificate':
            session_kwargs['cert_pem'] = self.cert_pem_path
            session_kwargs['cert_key_pem'] = self.cert_key_path

        self.session = Session(
            self.endpoint,
            auth=(self.username, self.password),
            **session_kwargs,
        )

        logger.info(
            "初始化WinRM客户端: 主机=%s, 端口=%s, SSL=%s, 认证=%s, 超时=%s秒",
            self.hostname, self.port, self.use_ssl, self.auth_method, self.timeout,
        )

    def _validate_hostname(self) -> bool:
        """验证主机名是否可以解析"""
        try:
            socket.gethostbyname(self.hostname)
            return True
        except socket.gaierror:
            logger.error("无法解析主机名: %s:%s", self.hostname, self.port)
            return False
        except Exception as e:
            logger.error("验证主机名时发生未知错误: %s", str(e))
            return False

    def execute_command(
        self,
        command: str,
        arguments: Optional[list] = None,
    ) -> WinrmResult:
        """执行远程命令"""
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info("DEMO模式: 模拟执行远程命令: %s", command)
            return WinrmResult(status_code=0, std_out="Command executed successfully in demo mode", std_err="")

        logger.info("执行远程命令: %s", command)

        for attempt in range(self.max_retries):
            try:
                result = self.session.run_cmd(command, arguments or [])
                winrm_result = WinrmResult(
                    status_code=result.status_code,
                    std_out=result.std_out.decode('utf-8', errors='ignore'),
                    std_err=result.std_err.decode('utf-8', errors='ignore'),
                )
                if winrm_result.success:
                    logger.info("命令执行成功: %s", command)
                else:
                    logger.warning(
                        "命令执行返回非零状态码: %s, 状态码=%s, 错误=%s",
                        command, result.status_code, winrm_result.std_err,
                    )
                return winrm_result
            except Exception as e:
                error_str = str(e)
                if "NameResolutionError" in error_str or "Failed to resolve" in error_str:
                    logger.error("主机名解析失败: %s", self.hostname)
                    raise Exception(f'主机名解析失败: 无法解析主机名 "{self.hostname}". 请检查主机名拼写或网络连接.')

                logger.error(
                    "命令执行失败 (尝试 %d/%d): %s, 错误: %s",
                    attempt + 1, self.max_retries, command, str(e),
                )
                if attempt == self.max_retries - 1:
                    raise Exception(f'命令执行失败: {str(e)}')
                time.sleep(1)

    def execute_powershell(
        self,
        script: str,
        arguments: Optional[dict] = None,
    ) -> WinrmResult:
        """执行 PowerShell 脚本"""
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            logger.info("DEMO模式: 模拟执行PowerShell脚本")
            return WinrmResult(
                status_code=0,
                std_out="PowerShell script executed successfully in demo mode",
                std_err="",
            )

        logger.info("执行PowerShell脚本")

        for attempt in range(self.max_retries):
            try:
                result = self.session.run_ps(script)
                winrm_result = WinrmResult(
                    status_code=result.status_code,
                    std_out=result.std_out.decode('utf-8', errors='ignore'),
                    std_err=result.std_err.decode('utf-8', errors='ignore'),
                )
                if winrm_result.success:
                    logger.info("PowerShell脚本执行成功")
                else:
                    logger.warning(
                        "PowerShell脚本执行返回非零状态码: 状态码=%s, 错误=%s",
                        result.status_code, winrm_result.std_err,
                    )
                return winrm_result
            except Exception as e:
                error_str = str(e)
                if "NameResolutionError" in error_str or "Failed to resolve" in error_str:
                    logger.error("主机名解析失败: %s", self.hostname)
                    raise Exception(f'主机名解析失败: 无法解析主机名 "{self.hostname}"')

                logger.error(
                    "PowerShell脚本执行失败 (尝试 %d/%d), 错误: %s",
                    attempt + 1, self.max_retries, str(e),
                )
                if attempt == self.max_retries - 1:
                    raise Exception(f'PowerShell执行失败: {str(e)}')
                time.sleep(1)

    def create_user(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> WinrmResult:
        """创建 Windows 本地用户"""
        try:
            validate_username(username)
            validate_string_length(password, 256, "密码")
            if description:
                validate_string_length(description, 512, "描述")
            if group:
                validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return WinrmResult(1, '', str(e))

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

        logger.info("创建用户: %s", username)
        result = self.execute_powershell(script)
        self.add_to_remote_users(username)
        return result

    def delete_user(self, username: str) -> WinrmResult:
        """删除 Windows 本地用户"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Remove-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("删除用户: %s", username)
        return self.execute_powershell(script)

    def enable_user(self, username: str) -> WinrmResult:
        """启用 Windows 本地用户"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Enable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("启用用户: %s", username)
        return self.execute_powershell(script)

    def disabled_user(self, username: str) -> WinrmResult:
        """禁用 Windows 本地用户"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'Disable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info("禁用用户: %s", username)
        return self.execute_powershell(script)

    def reset_password(self, username: str, password: str) -> WinrmResult:
        """重置 Windows 用户密码"""
        try:
            validate_username(username)
            validate_string_length(password, 256, "密码")
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", str(e))
            return WinrmResult(1, '', str(e))
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

    def op_user(self, username: str) -> WinrmResult:
        """将用户添加到 Administrators 组"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'net localgroup Administrators "{safe_user}" /add'
        logger.info("提升用户为管理员: %s", username)
        return self.execute_powershell(script)

    def deop_user(self, username: str) -> WinrmResult:
        """从 Administrators 组移除用户"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = f'net localgroup Administrators "{safe_user}" /delete'
        logger.info("取消用户管理员: %s", username)
        return self.execute_powershell(script)

    def add_to_remote_users(self, username: str) -> WinrmResult:
        """将用户添加到 Remote Desktop Users 组"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            return WinrmResult(1, '', str(e))
        safe_user = _escape_ps_string(username)
        script = (
            f'Add-LocalGroupMember -Group "Remote Desktop Users" '
            f'-Member "{safe_user}" -ErrorAction SilentlyContinue'
        )
        return self.execute_powershell(script)

    def check_user_exists(self, username: str) -> WinrmResult:
        """检查用户是否存在"""
        try:
            validate_username(username)
        except CommandInjectionError as e:
            return WinrmResult(1, '', str(e))
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

        logger.info("生成强密码完成，长度: %d", len(password))
        return password

    def get_password_policy(self) -> dict:
        """获取远程主机密码策略"""
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

            logger.info("获取密码策略成功: %s", policy)
            return policy
        except Exception as e:
            logger.error("获取密码策略失败: %s", str(e))
            return {
                "minimum_length": 8,
                "complexity_required": True,
                "history_size": 0,
                "max_age_days": 42,
                "min_age_days": 1,
            }
