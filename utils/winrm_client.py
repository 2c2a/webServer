# Winrm客户端工具
import logging
import re
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from winrm import Session
from winrm.exceptions import InvalidCredentialsError
from django.conf import settings
import socket
import time
import secrets
import string
import functools

logger = logging.getLogger("2c2a")


USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]{1,150}$")
GROUPNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\s]{1,256}$")
MAX_STRING_LENGTH = 4096


class CommandInjectionError(Exception):
    pass


def validate_username(username: str) -> str:
    if not username:
        raise CommandInjectionError("用户名不能为空")
    if len(username) > 150:
        raise CommandInjectionError("用户名长度不能超过150个字符")
    if not USERNAME_PATTERN.match(username):
        raise CommandInjectionError(f"用户名格式无效: 只允许字母、数字和下划线")
    return username


def validate_groupname(group: str) -> str:
    if not group:
        raise CommandInjectionError("组名不能为空")
    if len(group) > 256:
        raise CommandInjectionError("组名长度不能超过256个字符")
    if not GROUPNAME_PATTERN.match(group):
        raise CommandInjectionError(
            f"组名格式无效: 只允许字母、数字、下划线、连字符和空格"
        )
    return group


def validate_string_length(
    s: str, max_length: int = MAX_STRING_LENGTH, field_name: str = "输入"
) -> str:
    if s and len(s) > max_length:
        raise CommandInjectionError(f"{field_name}长度不能超过{max_length}个字符")
    return s


def _escape_ps_string(s: str) -> str:
    if not s:
        return s
    if len(s) > MAX_STRING_LENGTH:
        raise CommandInjectionError(f"字符串长度超过最大限制 {MAX_STRING_LENGTH}")
    return (
        s.replace("\x00", "")
        .replace("`", "``")
        .replace('"', '`"')
        .replace("$", "`$")
        .replace("\n", "`n")
        .replace("\r", "`r")
    )


def _escape_for_here_string(s: str) -> str:
    if not s:
        return s
    s = s.replace("\x00", "")
    if '@"' in s or '"@' in s:
        raise CommandInjectionError("内容包含非法的 here-string 分隔符")
    return s


@dataclass
class WinrmResult:
    status_code: int
    std_out: str
    std_err: str

    @property
    def success(self) -> bool:
        return self.status_code == 0


class WinrmClient:
    """WinRM客户端 - 远程管理Windows主机"""

    def __init__(
        self,
        hostname: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        port: int = 5985,
        use_ssl: bool = False,
        auth_method: str = "ntlm",
        cert_pem_path: Optional[str] = None,
        cert_key_path: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        server_cert_validation: str = "validate",
        ca_trust_path: Optional[str] = None,
        client_cert_pem: Optional[str] = None,
        client_cert_key: Optional[str] = None,
    ):
        """
        初始化WinRM客户端

        参数:
            hostname: 主机名或IP地址
            username: 登录用户名(ntlm方式必填)
            password: 登录密码(ntlm方式必填)
            port: WinRM服务端口，默认为5985
            use_ssl: 是否使用SSL连接，默认为False
            auth_method: 认证方式 ('ntlm', 'certificate')
            cert_pem_path: 客户端证书PEM文件路径(certificate方式必填)
            cert_key_path: 客户端私钥PEM文件路径(certificate方式必填)
            timeout: 操作超时时间（秒），默认使用配置文件中的值
            max_retries: 最大重试次数，默认使用配置文件中的值
            server_cert_validation: 服务器证书验证模式 ('ignore', 'validate')
            ca_trust_path: CA证书路径（用于验证服务器证书）
            client_cert_pem: 客户端证书PEM文件路径(已弃用，使用cert_pem_path)
            client_cert_key: 客户端证书私钥文件路径(已弃用，使用cert_key_path)
        """
        if auth_method == "certificate":
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
            self.auth_method = "certificate"
            self.cert_pem_path = cert_pem_path
            self.cert_key_path = cert_key_path
            self.username = username or ""
            self.password = password or ""
        elif auth_method == "ntlm":
            if not username:
                raise ValueError("NTLM认证方式必须提供用户名")
            if not password:
                raise ValueError("NTLM认证方式必须提供密码")
            self.auth_method = "ntlm"
            self.username = username
            self.password = password
            self.cert_pem_path = ""
            self.cert_key_path = ""
        else:
            raise ValueError(f"不支持的认证方式: {auth_method}")
        # 检查主机名是否包含端口（例如 "hostname:port" 或 "ip:port" 格式）
        if ":" in hostname and not hostname.startswith("http"):
            # 分离主机名和端口
            parts = hostname.split(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                # 提取主机名和端口
                actual_hostname = parts[0]
                actual_port = int(parts[1])
                # 更新实例变量
                self.hostname = actual_hostname
                # 如果没有显式指定端口，则使用从主机名中提取的端口
                if port == 5985:  # 5985是默认WinRM端口
                    self.port = actual_port
                else:
                    # 如果已显式指定端口，则使用指定的端口
                    self.port = port
            else:
                self.hostname = hostname
                self.port = port
        else:
            self.hostname = hostname
            self.port = port

        self.use_ssl = use_ssl
        self.timeout = timeout or settings.WINRM_TIMEOUT
        self.max_retries = max_retries or settings.WINRM_MAX_RETRIES

        self.server_cert_validation = server_cert_validation
        self.ca_trust_path = ca_trust_path
        self.client_cert_pem = client_cert_pem
        self.client_cert_key = client_cert_key

        if server_cert_validation == "ignore":
            logger.warning(
                f"WinRM连接到 {hostname} 未启用服务器证书验证，" "存在中间人攻击风险"
            )

        if use_ssl and server_cert_validation == "validate":
            if not ca_trust_path:
                logger.warning("SSL验证启用但未提供CA证书路径，将使用系统默认证书")
            elif not os.path.exists(ca_trust_path):
                logger.error(f"CA证书文件不存在: {ca_trust_path}")
                raise ValueError(f"CA证书文件不存在: {ca_trust_path}")

        if self.auth_method == "certificate":
            transport = "certificate"
            if not self.use_ssl:
                self.use_ssl = True
            if self.port == 5985:
                self.port = 5986
        else:
            transport = "ntlm"

        protocol = "https" if self.use_ssl else "http"
        self.endpoint = f"{protocol}://{self.hostname}:{self.port}/wsman"

        if not self._validate_hostname():
            raise ValueError(f"主机名无法解析: {self.hostname}")

        session_kwargs = dict(
            transport=transport,
            server_cert_validation=self.server_cert_validation,
            ca_trust_path=self.ca_trust_path or None,
            operation_timeout_sec=self.timeout,
            read_timeout_sec=self.timeout + 10,
        )
        if self.auth_method == "certificate":
            session_kwargs["cert_pem"] = self.cert_pem_path
            session_kwargs["cert_key_pem"] = self.cert_key_path
            self.session = Session(
                self.endpoint,
                auth=(self.username, self.password),
                **session_kwargs,
            )
        else:
            self.session = Session(
                self.endpoint,
                auth=(self.username, self.password),
                **session_kwargs,
            )

        logger.info(
            f"初始化WinRM客户端: 主机={self.hostname}, 端口={self.port}, "
            f"SSL={self.use_ssl}, 认证={self.auth_method}, "
            f"超时={self.timeout}秒, 最大重试={self.max_retries}次"
        )

    def _validate_hostname(self) -> bool:
        """
        验证主机名是否可以解析

        Returns:
            bool: 如果主机名可以解析则返回True，否则返回False
        """
        try:
            # 尝试解析主机名
            socket.gethostbyname(self.hostname)
            return True
        except socket.gaierror:
            logger.error(f"无法解析主机名: {self.hostname}:{self.port}")
            return False
        except Exception as e:
            logger.error(f"验证主机名时发生未知错误: {str(e)}")
            return False

    def execute_command(
        self, command: str, arguments: Optional[list] = None
    ) -> WinrmResult:
        """
        执行远程命令

        参数:
            command: 要执行的命令
            arguments: 命令参数列表

        返回:
            WinrmResult对象，包含执行结果

        异常:
            Exception: 当所有重试尝试都失败时抛出
        """
        import os

        # 如果是DEMO模式，模拟执行命令而不实际执行
        if os.environ.get("2C2A_DEMO", "").lower() == "1":
            logger.info(f"DEMO模式: 模拟执行远程命令: {command}, 参数: {arguments}")
            # 模拟成功执行的结果
            return WinrmResult(
                status_code=0,
                std_out="Command executed successfully in demo mode",
                std_err="",
            )

        logger.info(f"执行远程命令: {command}, 参数: {arguments}")

        for attempt in range(self.max_retries):
            try:
                result = self.session.run_cmd(command, arguments or [])
                winrm_result = WinrmResult(
                    status_code=result.status_code,
                    std_out=result.std_out.decode("utf-8", errors="ignore"),
                    std_err=result.std_err.decode("utf-8", errors="ignore"),
                )

                if winrm_result.success:
                    logger.info(f"命令执行成功: {command}")
                else:
                    logger.warning(
                        f"命令执行返回非零状态码: {command}, "
                        f"状态码={result.status_code}, 错误={winrm_result.std_err}"
                    )

                return winrm_result
            except Exception as e:
                # 检查是否是网络连接错误
                error_str = str(e)
                if (
                    "NameResolutionError" in error_str
                    or "Failed to resolve" in error_str
                ):
                    logger.error(f"主机名解析失败: {self.hostname}")
                    raise Exception(
                        f'主机名解析失败: 无法解析主机名 "{self.hostname}". 请检查主机名拼写或网络连接.'
                    )

                logger.error(
                    f"命令执行失败 (尝试 {attempt + 1}/{self.max_retries}): "
                    f"{command}, 错误: {str(e)}"
                )

                if attempt == self.max_retries - 1:
                    logger.error(f"命令执行最终失败: {command}")
                    raise Exception(f"命令执行失败: {str(e)}")

                # 在重试之间等待一段时间
                time.sleep(1)

    def execute_powershell(
        self, script: str, arguments: Optional[Dict[str, Any]] = None
    ) -> WinrmResult:
        """
        执行PowerShell脚本

        参数:
            script: 要执行的PowerShell脚本
            arguments: 脚本参数字典

        返回:
            WinrmResult对象，包含执行结果

        异常:
            Exception: 当所有重试尝试都失败时抛出
        """
        import os

        # 如果是DEMO模式，模拟执行PowerShell而不实际执行
        if os.environ.get("2C2A_DEMO", "").lower() == "1":
            logger.info("DEMO模式: 模拟执行PowerShell脚本")
            # 模拟成功执行的结果
            return WinrmResult(
                status_code=0,
                std_out="PowerShell script executed successfully in demo mode",
                std_err="",
            )

        logger.info(f"执行远程命令: {script}, 参数: {arguments}")

        for attempt in range(self.max_retries):
            try:
                result = self.session.run_ps(script)
                winrm_result = WinrmResult(
                    status_code=result.status_code,
                    std_out=result.std_out.decode("utf-8", errors="ignore"),
                    std_err=result.std_err.decode("utf-8", errors="ignore"),
                )

                if winrm_result.success:
                    logger.info(f"PowerShell脚本执行成功")
                else:
                    logger.warning(
                        f"PowerShell脚本执行返回非零状态码: "
                        f"状态码={result.status_code}, 错误={winrm_result.std_err}"
                    )

                return winrm_result
            except Exception as e:
                # 检查是否是网络连接错误
                error_str = str(e)
                if (
                    "NameResolutionError" in error_str
                    or "Failed to resolve" in error_str
                ):
                    logger.error(f"主机名解析失败: {self.hostname}")
                    raise Exception(
                        f'主机名解析失败: 无法解析主机名 "{self.hostname}". 请检查主机名拼写或网络连接.'
                    )

                logger.error(
                    f"PowerShell脚本执行失败 (尝试 {attempt + 1}/{self.max_retries}), "
                    f"错误: {str(e)}"
                )

                if attempt == self.max_retries - 1:
                    logger.error("PowerShell脚本执行最终失败")
                    raise Exception(f"PowerShell执行失败: {str(e)}")

                # 在重试之间等待一段时间
                time.sleep(1)

    def create_user(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> WinrmResult:
        try:
            validate_username(username)
            validate_string_length(password, 256, "密码")
            if description:
                validate_string_length(description, 512, "描述")
            if group:
                validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))

        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        safe_desc = _escape_ps_string(description or "")

        script = f"""
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
New-LocalUser -Name "{safe_user}" -Password $pw -Description "{safe_desc}" -ErrorAction Stop
net user "{safe_user}" /logonpasswordchg:NO
Add-LocalGroupMember -Group "Users" -Member "{safe_user}" -ErrorAction Stop
"""
        if group:
            safe_group = _escape_ps_string(group)
            script += f'Add-LocalGroupMember -Group "{safe_group}" -Member "{safe_user}" -ErrorAction Stop\n'

        logger.info(f"创建用户: {username}")
        result = self.execute_powershell(script)
        self.add_to_remote_users(username)
        return result

    def create_user_with_reset_password_on_next_login(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> WinrmResult:
        try:
            validate_username(username)
            validate_string_length(password, 256, "密码")
            if description:
                validate_string_length(description, 512, "描述")
            if group:
                validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))

        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        safe_desc = _escape_ps_string(description or "")

        script = f"""
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
New-LocalUser -Name "{safe_user}" -Password $pw -Description "{safe_desc}" -ErrorAction Stop
net user "{safe_user}" /logonpasswordchg:NO
Add-LocalGroupMember -Group "Users" -Member "{safe_user}" -ErrorAction Stop
"""
        if group:
            safe_group = _escape_ps_string(group)
            script += f'Add-LocalGroupMember -Group "{safe_group}" -Member "{safe_user}" -ErrorAction Stop\n'

        logger.info(f"创建用户(首登改密): {username}")
        result = self.execute_powershell(script)
        self.add_to_remote_users(username)
        return result

    def delete_user(self, username: str) -> WinrmResult:
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        script = f'Remove-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info(f"删除用户: {username}")
        return self.execute_powershell(script)

    def enable_user(self, username: str) -> WinrmResult:
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        script = f'Enable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info(f"启用用户: {username}")
        return self.execute_powershell(script)

    def disabled_user(self, username: str) -> WinrmResult:
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        script = f'Disable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        logger.info(f"禁用用户: {username}")
        return self.execute_powershell(script)

    def get_user_info(self, username: str) -> WinrmResult:
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        script = f'Get-LocalUser -Name "{safe_user}" | ConvertTo-Json'
        return self.execute_powershell(script)

    def list_users(self) -> WinrmResult:
        return self.execute_powershell("Get-LocalUser | ConvertTo-Json")

    def check_user_exists(self, username: str) -> bool:
        try:
            validate_username(username)
        except CommandInjectionError:
            return False
        safe_user = _escape_ps_string(username)
        try:
            script = f'$u = Get-LocalUser -Name "{safe_user}" -ErrorAction Stop; $true'
            result = self.execute_powershell(script)
            return result.success and "True" in result.std_out
        except:
            return False

    def get_password_policy(self) -> Dict[str, Any]:
        """
        动态获取密码策略要求

        返回:
            Dict: 包含密码策略信息的字典
        """
        try:
            script = f"""
            secedit /export /cfg "$env:TEMP\\secpol.cfg" | Out-Null
            Get-Content "$env:TEMP\\secpol.cfg" | Where-Object {{ $_ -match '^(MinimumPasswordLength|PasswordComplexity|PasswordHistorySize|MaximumPasswordAge|MinimumPasswordAge)\\s*=' }}
            Remove-Item "$env:TEMP\\secpol.cfg" -ErrorAction SilentlyContinue
            """
            result = self.execute_powershell(script)

            policy = {}
            if result.success:
                lines = result.std_out.strip().split("\n")
                for line in lines:
                    line = line.strip()
                    if line.startswith("MinimumPasswordLength"):
                        try:
                            policy["minimum_length"] = int(line.split("=")[1].strip())
                        except:
                            policy["minimum_length"] = 8  # 默认值
                    elif line.startswith("PasswordComplexity"):
                        try:
                            policy["complexity_required"] = bool(
                                int(line.split("=")[1].strip())
                            )
                        except:
                            policy["complexity_required"] = True  # 默认值
                    elif line.startswith("PasswordHistorySize"):
                        try:
                            policy["history_size"] = int(line.split("=")[1].strip())
                        except:
                            policy["history_size"] = 0  # 默认值
                    elif line.startswith("MaximumPasswordAge"):
                        try:
                            policy["max_age_days"] = int(line.split("=")[1].strip())
                        except:
                            policy["max_age_days"] = 0  # 默认值
                    elif line.startswith("MinimumPasswordAge"):
                        try:
                            policy["min_age_days"] = int(line.split("=")[1].strip())
                        except:
                            policy["min_age_days"] = 0  # 默认值

            # 设置默认值
            if "minimum_length" not in policy:
                policy["minimum_length"] = 8
            if "complexity_required" not in policy:
                policy["complexity_required"] = True

            logger.info(f"获取密码策略成功: {policy}")
            return policy
        except Exception as e:
            logger.error(f"获取密码策略失败: 错误: {str(e)}")
            # 返回默认密码策略
            return {
                "minimum_length": 8,
                "complexity_required": True,
                "history_size": 0,
                "max_age_days": 42,
                "min_age_days": 1,
            }

    def generate_strong_password(self, length: Optional[int] = None) -> str:
        """
        根据密码策略生成强密码

        参数:
            length: 密码长度，默认根据服务器策略确定

        返回:
            str: 生成的强密码
        """
        import secrets
        import string

        # 获取服务器密码策略
        policy = self.get_password_policy()

        # 确定密码长度
        actual_length = length or max(policy["minimum_length"], 12)  # 默认至少12位

        if policy["complexity_required"]:
            # 密码复杂性要求：至少包含大写字母、小写字母、数字和特殊字符
            uppercase = secrets.choice(string.ascii_uppercase)
            lowercase = secrets.choice(string.ascii_lowercase)
            digit = secrets.choice(string.digits)
            special_char = secrets.choice("!@#$%^&*()_+-=[]{}|;:,.<>?")

            # 剩余部分随机生成
            remaining_length = max(0, actual_length - 4)
            alphabet = (
                string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
            )
            rest = "".join(secrets.choice(alphabet) for i in range(remaining_length))

            # 打乱顺序以确保安全
            password_chars = list(uppercase + lowercase + digit + special_char + rest)
            secrets.SystemRandom().shuffle(password_chars)
            password = "".join(password_chars)
        else:
            # 不需要复杂性要求，简单生成随机密码
            alphabet = string.ascii_letters + string.digits
            password = "".join(secrets.choice(alphabet) for i in range(actual_length))

        logger.info(f"生成强密码完成，长度: {len(password)}")
        return password

    def op_user(self, username: str) -> bool:
        try:
            validate_username(username)
        except CommandInjectionError:
            return False
        safe_user = _escape_ps_string(username)
        try:
            result = self.execute_powershell(
                f'net localgroup Administrators "{safe_user}" /add'
            )
            return result.success
        except:
            return False

    def deop_user(self, username: str) -> bool:
        try:
            validate_username(username)
        except CommandInjectionError:
            return False
        safe_user = _escape_ps_string(username)
        try:
            result = self.execute_powershell(
                f'net localgroup Administrators "{safe_user}" /delete'
            )
            return result.success
        except:
            return False

    def reset_password(self, username: str, password: str) -> WinrmResult:
        try:
            validate_username(username)
            validate_string_length(password, 256, "密码")
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        script = f"""
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
Set-LocalUser -Name "{safe_user}" -Password $pw
net user "{safe_user}" /logonpasswordchg:NO
"""
        result = self.execute_powershell(script)
        if result.success:
            self.add_to_remote_users(username)
        return result

    def add_to_remote_users(self, username: str) -> WinrmResult:
        try:
            validate_username(username)
        except CommandInjectionError as e:
            logger.warning(f"输入验证失败: {str(e)}")
            return WinrmResult(1, "", str(e))
        safe_user = _escape_ps_string(username)
        script = (
            f'Add-LocalGroupMember -Group "Remote Desktop Users" '
            f'-Member "{safe_user}" -ErrorAction SilentlyContinue'
        )
        return self.execute_powershell(script)
