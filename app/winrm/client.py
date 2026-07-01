"""高层异步 WinRM 客户端，封装命令执行与用户管理。

基于 :class:`app.winrm.transport.WinRMTransport` 实现 WS-Management 协议交互，
对外提供与同步 ``utils.winrm_client.WinrmClient`` 一致的方法集合（异步版）。

设计要点
--------
- 全异步，绝不阻塞事件循环（aiohttp + ``asyncio.sleep``）
- 连接池复用（由 transport 维护 ``aiohttp.ClientSession``，limit=10）
- demo 模式短路：所有 ``execute_*`` 直接返回模拟成功结果（对应 2C2A_DEMO 模式）
- 注入防护：用户名白名单 + PowerShell 字符串转义 + here-string 防护
"""
from __future__ import annotations

import asyncio
import base64
import logging
import secrets
import string
from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

from app.winrm.commands import (
    ADD_TO_REMOTE_USERS_PS,
    CHECK_USER_EXISTS_PS,
    CREATE_USER_PS,
    CREATE_USER_RESET_PS,
    DELETE_USER_PS,
    DISABLE_USER_PS,
    ENABLE_USER_PS,
    GET_PASSWORD_POLICY_PS,
    GET_USER_INFO_PS,
    GRANT_ADMIN_PS,
    LIST_USERS_PS,
    RESET_PASSWORD_PS,
    REVOKE_ADMIN_PS,
    escape_ps_string,
    validate_groupname,
    validate_username,
)
from app.winrm.transport import (
    ACTION_COMMAND,
    ACTION_CREATE,
    ACTION_DELETE,
    ACTION_RECEIVE,
    ACTION_SIGNAL,
    RSRC_CMD,
    SIGNAL_TERMINATE,
    WinRMTransport,
    WinRMTransportError,
)

logger = logging.getLogger("2c2a")

# 默认密码策略（获取失败或 demo 模式时使用）
DEFAULT_PASSWORD_POLICY = {
    "minimum_length": 8,
    "complexity_required": True,
    "history_size": 0,
    "max_age_days": 42,
    "min_age_days": 1,
}


class CommandInjectionError(Exception):
    """命令注入防护异常。

    当用户名 / 组名 / 字符串未通过白名单或转义校验时抛出。
    """


@dataclass
class WinRMResult:
    """WinRM 命令执行结果。

    ``demo_mode=True`` 表示本次结果为 demo 模式模拟返回，未实际执行远程命令。
    调用方应将其透传给前端，以便用户感知"演示成功"与"真实成功"的区别。
    """

    status_code: int
    std_out: str
    std_err: str
    # demo 模式标记：True 表示本次结果为模拟返回，未实际执行远程命令
    demo_mode: bool = False

    @property
    def success(self) -> bool:
        """状态码为 0 视为成功（含 demo 模式模拟成功）。

        注意：demo 模式下 success=True 仅表示"模拟操作完成"，不代表真实执行。
        如需区分真实成功，请检查 ``demo_mode`` 字段。
        """
        return self.status_code == 0


def _safe_int(line: str, default: int) -> int:
    """从 ``Key = Value`` 形式的行中安全解析整数，失败返回默认值。"""
    try:
        return int(line.split("=", 1)[1].strip())
    except (IndexError, ValueError):
        return default


class AsyncWinRMClient:
    """异步 WinRM 客户端。

    用法::

        async with AsyncWinRMClient("10.0.0.1", username="admin", password="***") as c:
            result = await c.execute_command("whoami")
            if result.success:
                print(result.std_out)
    """

    def __init__(
        self,
        host: str,
        port: int = 5985,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_method: str = "ntlm",
        use_ssl: bool = False,
        cert_pem_path: Optional[str] = None,
        cert_key_path: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        demo: bool = False,
    ):
        """
        :param host: 主机名或 IP 地址
        :param port: WinRM 端口，默认 5985（HTTP）；HTTPS 通常为 5986
        :param username: 登录用户名（NTLM 必填）
        :param password: 登录密码（NTLM 必填）
        :param auth_method: 认证方式，``ntlm`` 或 ``certificate``
        :param use_ssl: 是否使用 SSL
        :param cert_pem_path: 客户端证书 PEM 路径（证书认证必填）
        :param cert_key_path: 客户端私钥 PEM 路径（证书认证必填）
        :param timeout: 单次请求超时（秒）
        :param max_retries: 失败最大重试次数
        :param demo: demo 模式，所有方法返回模拟成功结果，不实际连接
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.auth_method = auth_method
        self.use_ssl = use_ssl
        self.cert_pem_path = cert_pem_path
        self.cert_key_path = cert_key_path
        self.timeout = timeout
        self.max_retries = max_retries
        # demo 模式：显式传入或跟随全局 settings.demo（统一配置源，不再直读环境变量）
        if demo:
            self.demo = True
        else:
            from app.core.config import settings

            self.demo = settings.demo

        # 缓存的密码策略，供同步方法 generate_strong_password 使用
        self._cached_policy: Optional[dict] = None

        # 构造认证信息与端点
        if auth_method == "ntlm":
            if not username or not password:
                raise ValueError("NTLM 认证必须提供用户名和密码")
            auth = {"method": "ntlm", "username": username, "password": password}
            verify_ssl = True
        elif auth_method == "certificate":
            if not cert_pem_path or not cert_key_path:
                raise ValueError("证书认证必须提供证书和私钥路径")
            # 证书认证强制 SSL
            if not self.use_ssl:
                self.use_ssl = True
            auth = {
                "method": "certificate",
                "cert_pem_path": cert_pem_path,
                "key_pem_path": cert_key_path,
                "username": username or "",
            }
            verify_ssl = True
        else:
            raise ValueError(f"不支持的认证方式: {auth_method}")

        protocol = "https" if self.use_ssl else "http"
        self.endpoint = f"{protocol}://{host}:{port}/wsman"

        self._transport = WinRMTransport(
            endpoint=self.endpoint,
            auth=auth,
            timeout=timeout,
            max_retries=max_retries,
            use_ssl=self.use_ssl,
            verify_ssl=verify_ssl,
        )

        logger.info(
            "初始化异步 WinRM 客户端: host=%s, port=%s, ssl=%s, auth=%s, demo=%s",
            host,
            port,
            self.use_ssl,
            auth_method,
            self.demo,
        )

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------
    @classmethod
    async def from_host_config(cls, host) -> "AsyncWinRMClient":
        """从 Host 模型（鸭子类型）构造客户端。

        ``host`` 需含属性: ``hostname`` / ``port`` / ``username`` / ``auth_method``
        / ``use_ssl``，以及加密的密码字段。

        密码字段是加密存储的，需调用
        ``app.security.field_cipher.decrypt_field`` 解密（字段名 ``host.password``）。
        证书认证时读取 ``cert_pem_path`` / ``cert_key_path``。

        为兼容不同实现，优先用 ``decrypt_field`` 解密原始 ``_password`` 字段，
        失败则回退到模型自身的 ``password`` 属性。
        """
        auth_method = getattr(host, "auth_method", "ntlm")
        use_ssl = getattr(host, "use_ssl", False)
        port = getattr(host, "port", 5986 if use_ssl else 5985)
        hostname = getattr(host, "hostname")
        username = getattr(host, "username", None) or None

        # 解密密码：优先用 field_cipher 解密原始加密字段
        password: Optional[str] = None
        encrypted = getattr(host, "password_cipher", None) or getattr(host, "_password", None)
        if encrypted:
            logger.info(
                "解密主机密码: password_cipher 长度=%d, field_name=host.password",
                len(encrypted),
            )
            try:
                from app.security.field_cipher import decrypt_field

                password = decrypt_field(encrypted, "host.password")
                logger.info("密码解密成功, 长度=%d", len(password) if password else 0)
            except Exception as e:  # noqa: BLE001
                logger.error("field_cipher 解密密码失败: %s", e)
                password = None
        else:
            logger.warning("主机 %s 无 password_cipher 字段", hostname)
        if not password:
            # 回退到模型自身的 password 属性（可能已解密）
            try:
                password = getattr(host, "password", None)
            except Exception:  # noqa: BLE001
                password = None

        cert_pem_path = getattr(host, "cert_pem_path", None) or None
        cert_key_path = getattr(host, "cert_key_path", None) or None

        return cls(
            host=hostname,
            port=port,
            username=username,
            password=password,
            auth_method=auth_method,
            use_ssl=use_ssl,
            cert_pem_path=cert_pem_path,
            cert_key_path=cert_key_path,
        )

    # ------------------------------------------------------------------
    # 注入防护
    # ------------------------------------------------------------------
    def _validate_username(self, username: str) -> str:
        """用户名白名单校验，无效抛 :class:`CommandInjectionError`。"""
        try:
            return validate_username(username)
        except ValueError as e:
            raise CommandInjectionError(str(e)) from e

    def _validate_groupname(self, group: str) -> str:
        """组名校验，无效抛 :class:`CommandInjectionError`。"""
        try:
            return validate_groupname(group)
        except ValueError as e:
            raise CommandInjectionError(str(e)) from e

    def _escape_ps_string(self, s: str) -> str:
        """PowerShell 字符串转义，超长抛 :class:`CommandInjectionError`。"""
        try:
            return escape_ps_string(s)
        except ValueError as e:
            raise CommandInjectionError(str(e)) from e

    def _escape_for_here_string(self, s: str) -> str:
        """防止 here-string 注入：禁止出现 ``@"`` 与 ``"@`` 分隔符。"""
        if not s:
            return s
        s = s.replace("\x00", "")
        if '@"' in s or '"@' in s:
            raise CommandInjectionError("内容包含非法的 here-string 分隔符")
        return s

    # ------------------------------------------------------------------
    # demo 模式短路
    # ------------------------------------------------------------------
    def _demo_result(self, *, action: str = "") -> WinRMResult:
        """demo 模式统一返回的模拟成功结果。

        :param action: 本次模拟的操作名（用于日志/前端展示，如 "create_user"）
        """
        std_out = f"DEMO MODE: {action}" if action else "DEMO MODE"
        return WinRMResult(
            status_code=0,
            std_out=std_out,
            std_err="",
            demo_mode=True,
        )

    # ------------------------------------------------------------------
    # 命令执行（WS-Management 协议编排）
    # ------------------------------------------------------------------
    async def execute_command(
        self, command: str, arguments: Optional[list[str]] = None
    ) -> WinRMResult:
        """执行远程 cmd 命令。

        :param command: 命令名，如 ``whoami`` / ``cmd``
        :param arguments: 命令参数列表
        """
        if self.demo:
            logger.info("DEMO 模式: 模拟执行命令: %s %s", command, arguments)
            return self._demo_result(action=f"execute_command({command})")
        return await self._run_shell_command(RSRC_CMD, command, arguments or [])

    async def execute_powershell(self, script: str) -> WinRMResult:
        """执行 PowerShell 脚本。

        将脚本以 UTF-16LE 编码后 base64，通过
        ``powershell.exe -EncodedCommand`` 执行。这是 pywinrm 的标准做法，
        可正确处理 Unicode 与特殊字符，避免命令行转义问题。
        """
        if self.demo:
            logger.info("DEMO 模式: 模拟执行 PowerShell 脚本")
            return self._demo_result(action="execute_powershell")
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return await self._run_shell_command(
            RSRC_CMD,
            "powershell.exe",
            ["-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        )

    async def _run_shell_command(
        self, resource_uri: str, command: str, arguments: list[str]
    ) -> WinRMResult:
        """完整的 WS-Management 命令执行流程：建壳 -> 执行 -> 接收 -> 清理。"""
        shell_id: Optional[str] = None
        try:
            # 1. 创建 Shell
            shell_id = await self._create_shell(resource_uri)
            # 2. 执行命令，获取 command_id
            command_id = await self._send_command(
                resource_uri, shell_id, command, arguments
            )
            # 3. 接收输出（轮询直到结束）
            stdout, stderr, exit_code = await self._receive_output(
                resource_uri, shell_id, command_id
            )
            # 4. 发送终止信号
            await self._signal_command(resource_uri, shell_id, command_id)
            return WinRMResult(
                status_code=exit_code, std_out=stdout, std_err=stderr
            )
        except WinRMTransportError as e:
            logger.error("命令执行失败: %s", e)
            return WinRMResult(status_code=-1, std_out="", std_err=str(e))
        except Exception as e:  # noqa: BLE001
            logger.exception("命令执行异常")
            return WinRMResult(status_code=-1, std_out="", std_err=str(e))
        finally:
            if shell_id:
                try:
                    await self._delete_shell(resource_uri, shell_id)
                except Exception:  # noqa: BLE001
                    logger.warning("删除 Shell 失败: %s", shell_id, exc_info=True)

    async def _create_shell(self, resource_uri: str) -> str:
        """创建 Shell，返回 ShellId。

        OptionSet 必须包含 ``WINRS_NOPROFILE`` 与 ``WINRS_CODEPAGE``，
        否则 WS-Management 服务端返回 SchemaValidationError。
        """
        body = (
            "<rsp:Shell>"
            "<rsp:InputStreams>stdin</rsp:InputStreams>"
            "<rsp:OutputStreams>stdout stderr</rsp:OutputStreams>"
            "</rsp:Shell>"
        )
        envelope = self._transport._build_envelope(
            action=ACTION_CREATE,
            resource_uri=resource_uri,
            selectors=None,
            body=body,
            option_set={
                "WINRS_NOPROFILE": "FALSE",
                "WINRS_CODEPAGE": "437",
            },
        )
        resp = await self._transport.post(envelope)
        return self._parse_shell_id(resp)

    async def _send_command(
        self,
        resource_uri: str,
        shell_id: str,
        command: str,
        arguments: list[str],
    ) -> str:
        """发送命令，返回 CommandId。

        MS-WSMV 规范：Command action 的 Body 必须用 ``rsp:CommandLine`` 包裹，
        内含 ``rsp:Command``（命令名）与可选的 ``rsp:Arguments``（空格分隔的参数串）。
        OptionSet 必须包含 ``WINRS_CONSOLEMODE_STDIN`` 与 ``WINRS_SKIP_CMD_SHELL``。
        """
        # 参数以空格拼接为单个 rsp:Arguments 元素（pywinrm 兼容写法）
        args_xml = ""
        if arguments:
            unicode_args = [
                a if isinstance(a, str) else a.decode("utf-8") for a in arguments
            ]
            args_xml = (
                f"<rsp:Arguments>{xml_escape(' '.join(unicode_args))}</rsp:Arguments>"
            )
        body = (
            "<rsp:CommandLine>"
            f"<rsp:Command>{xml_escape(command)}</rsp:Command>"
            f"{args_xml}"
            "</rsp:CommandLine>"
        )
        envelope = self._transport._build_envelope(
            action=ACTION_COMMAND,
            resource_uri=resource_uri,
            selectors={"ShellId": shell_id},
            body=body,
            option_set={
                "WINRS_CONSOLEMODE_STDIN": "TRUE",
                "WINRS_SKIP_CMD_SHELL": "FALSE",
            },
        )
        resp = await self._transport.post(envelope)
        return self._parse_command_id(resp)

    async def _receive_output(
        self, resource_uri: str, shell_id: str, command_id: str
    ) -> tuple[str, str, int]:
        """轮询接收命令输出，返回 (stdout, stderr, exit_code)。

        使用 ``asyncio.sleep`` 间隔轮询，不阻塞事件循环；
        最大轮询次数由 timeout 限定，避免无限等待。
        """
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        exit_code = 0
        # 每 0.1s 轮询一次，最多持续 timeout 秒
        max_iterations = max(1, self.timeout * 10)
        done = False

        for _ in range(max_iterations):
            # MS-WSMV 规范：DesiredStream 通过 CommandId 属性关联命令，
            # 文本内容为 "stdout stderr"（空格分隔的流名）
            body = (
                "<rsp:Receive>"
                f'<rsp:DesiredStream CommandId="{xml_escape(command_id)}">'
                "stdout stderr"
                "</rsp:DesiredStream>"
                "</rsp:Receive>"
            )
            envelope = self._transport._build_envelope(
                action=ACTION_RECEIVE,
                resource_uri=resource_uri,
                selectors={"ShellId": shell_id},
                body=body,
            )
            resp = await self._transport.post(envelope)
            done, out, err, code = self._parse_receive_response(resp)
            if out:
                stdout_parts.append(out)
            if err:
                stderr_parts.append(err)
            if code is not None:
                exit_code = code
            if done:
                break
            await asyncio.sleep(0.1)
        else:
            logger.warning(
                "接收输出超时，shell=%s command=%s", shell_id, command_id
            )

        return "".join(stdout_parts), "".join(stderr_parts), exit_code

    async def _signal_command(
        self, resource_uri: str, shell_id: str, command_id: str
    ) -> None:
        """发送终止信号。

        MS-WSMV 规范：Signal 的 CommandId 通过属性传递，Code 为终止信号 URI。
        """
        body = (
            f'<rsp:Signal CommandId="{xml_escape(command_id)}">'
            f"<rsp:Code>{SIGNAL_TERMINATE}</rsp:Code>"
            "</rsp:Signal>"
        )
        envelope = self._transport._build_envelope(
            action=ACTION_SIGNAL,
            resource_uri=resource_uri,
            selectors={"ShellId": shell_id},
            body=body,
        )
        await self._transport.post(envelope)

    async def _delete_shell(
        self, resource_uri: str, shell_id: str
    ) -> None:
        """删除 Shell，释放服务端资源。"""
        envelope = self._transport._build_envelope(
            action=ACTION_DELETE,
            resource_uri=resource_uri,
            selectors={"ShellId": shell_id},
            body="",
        )
        await self._transport.post(envelope)

    # ------------------------------------------------------------------
    # SOAP 响应解析
    # ------------------------------------------------------------------
    @staticmethod
    def _local(tag: str) -> str:
        """去除命名空间前缀，返回本地标签名。"""
        return tag.split("}", 1)[-1] if "}" in tag else tag

    def _parse_shell_id(self, resp: str) -> str:
        """从 Create 响应中解析 ShellId。"""
        try:
            root = ET.fromstring(resp)
        except ET.ParseError as e:
            raise WinRMTransportError(f"解析 ShellId 响应失败: {e}") from e
        for elem in root.iter():
            if self._local(elem.tag) == "Selector" and elem.get("Name") == "ShellId":
                return elem.text or ""
            if self._local(elem.tag) == "ShellId":
                return elem.text or ""
        raise WinRMTransportError("无法从响应中解析 ShellId")

    def _parse_command_id(self, resp: str) -> str:
        """从 Command 响应中解析 CommandId。"""
        try:
            root = ET.fromstring(resp)
        except ET.ParseError as e:
            raise WinRMTransportError(f"解析 CommandId 响应失败: {e}") from e
        for elem in root.iter():
            if self._local(elem.tag) == "CommandId":
                return elem.text or ""
        raise WinRMTransportError("无法从响应中解析 CommandId")

    def _parse_receive_response(
        self, resp: str
    ) -> tuple[bool, str, str, Optional[int]]:
        """解析 Receive 响应。

        :returns: (是否结束, stdout 增量, stderr 增量, exit_code 或 None)
        """
        done = False
        out = ""
        err = ""
        exit_code: Optional[int] = None
        try:
            root = ET.fromstring(resp)
        except ET.ParseError:
            # 解析失败视为结束，避免死循环
            return True, "", "", None

        for elem in root.iter():
            tag = self._local(elem.tag)
            if tag == "Stream":
                name = elem.get("Name", "")
                text = elem.text or ""
                try:
                    decoded = base64.b64decode(text).decode(
                        "utf-8", errors="ignore"
                    )
                except Exception:  # noqa: BLE001
                    decoded = text
                if name == "stdout":
                    out += decoded
                elif name == "stderr":
                    err += decoded
            elif tag == "CommandState":
                state = elem.get("State", "")
                if "Done" in state or "Terminated" in state:
                    done = True
                    for child in elem:
                        if self._local(child.tag) == "ExitCode":
                            try:
                                exit_code = int((child.text or "0").strip())
                            except ValueError:
                                exit_code = 0
        return done, out, err, exit_code

    # ------------------------------------------------------------------
    # 用户管理方法（全部 async，内部调用 execute_powershell）
    # ------------------------------------------------------------------
    async def create_user(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> WinRMResult:
        """创建本地用户，并加入 Users 组与（可选）指定组。"""
        try:
            self._validate_username(username)
            self._escape_ps_string(password)
            if description:
                self._escape_ps_string(description)
            if group:
                self._validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))

        safe_user = self._escape_ps_string(username)
        safe_pass = self._escape_ps_string(password)
        safe_desc = self._escape_ps_string(description or "")
        extra_group = ""
        if group:
            safe_group = self._escape_ps_string(group)
            extra_group = (
                f'Add-LocalGroupMember -Group "{safe_group}" '
                f'-Member "{safe_user}" -ErrorAction Stop'
            )
        script = CREATE_USER_PS.format(
            username=safe_user,
            password=safe_pass,
            description=safe_desc,
            extra_group=extra_group,
        )
        logger.info("创建用户: %s", username)
        result = await self.execute_powershell(script)
        await self.add_to_remote_users(username)
        return result

    async def create_user_with_reset_password_on_next_login(
        self,
        username: str,
        password: str,
        description: Optional[str] = None,
        group: Optional[str] = None,
    ) -> WinRMResult:
        """创建本地用户，并要求首次登录时修改密码。"""
        try:
            self._validate_username(username)
            self._escape_ps_string(password)
            if description:
                self._escape_ps_string(description)
            if group:
                self._validate_groupname(group)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))

        safe_user = self._escape_ps_string(username)
        safe_pass = self._escape_ps_string(password)
        safe_desc = self._escape_ps_string(description or "")
        extra_group = ""
        if group:
            safe_group = self._escape_ps_string(group)
            extra_group = (
                f'Add-LocalGroupMember -Group "{safe_group}" '
                f'-Member "{safe_user}" -ErrorAction Stop'
            )
        script = CREATE_USER_RESET_PS.format(
            username=safe_user,
            password=safe_pass,
            description=safe_desc,
            extra_group=extra_group,
        )
        logger.info("创建用户(首登改密): %s", username)
        result = await self.execute_powershell(script)
        await self.add_to_remote_users(username)
        return result

    async def delete_user(self, username: str) -> WinRMResult:
        """删除本地用户。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = DELETE_USER_PS.format(username=safe_user)
        logger.info("删除用户: %s", username)
        return await self.execute_powershell(script)

    async def enable_user(self, username: str) -> WinRMResult:
        """启用本地用户。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = ENABLE_USER_PS.format(username=safe_user)
        logger.info("启用用户: %s", username)
        return await self.execute_powershell(script)

    async def disable_user(self, username: str) -> WinRMResult:
        """禁用本地用户。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = DISABLE_USER_PS.format(username=safe_user)
        logger.info("禁用用户: %s", username)
        return await self.execute_powershell(script)

    async def get_user_info(self, username: str) -> WinRMResult:
        """获取单个用户信息（JSON）。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = GET_USER_INFO_PS.format(username=safe_user)
        return await self.execute_powershell(script)

    async def list_users(self) -> WinRMResult:
        """列出所有本地用户（JSON）。"""
        return await self.execute_powershell(LIST_USERS_PS)

    async def check_user_exists(self, username: str) -> bool:
        """检查用户是否存在。"""
        try:
            self._validate_username(username)
        except CommandInjectionError:
            return False
        safe_user = self._escape_ps_string(username)
        try:
            script = CHECK_USER_EXISTS_PS.format(username=safe_user)
            result = await self.execute_powershell(script)
            return result.success and "True" in result.std_out
        except Exception:  # noqa: BLE001
            return False

    async def reset_password(self, username: str, password: str) -> WinRMResult:
        """重置用户密码。"""
        try:
            self._validate_username(username)
            self._escape_ps_string(password)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        safe_pass = self._escape_ps_string(password)
        script = RESET_PASSWORD_PS.format(
            username=safe_user, password=safe_pass
        )
        result = await self.execute_powershell(script)
        if result.success:
            await self.add_to_remote_users(username)
        return result

    async def add_to_remote_users(self, username: str) -> WinRMResult:
        """加入 Remote Desktop Users 组。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = ADD_TO_REMOTE_USERS_PS.format(username=safe_user)
        return await self.execute_powershell(script)

    async def grant_admin_privileges(self, username: str) -> WinRMResult:
        """授予管理员权限（加入 Administrators 组）。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = GRANT_ADMIN_PS.format(username=safe_user)
        logger.info("授予管理员权限: %s", username)
        return await self.execute_powershell(script)

    async def revoke_admin_privileges(self, username: str) -> WinRMResult:
        """撤销管理员权限（移出 Administrators 组）。"""
        try:
            self._validate_username(username)
        except CommandInjectionError as e:
            logger.warning("输入验证失败: %s", e)
            return WinRMResult(1, "", str(e))
        safe_user = self._escape_ps_string(username)
        script = REVOKE_ADMIN_PS.format(username=safe_user)
        logger.info("撤销管理员权限: %s", username)
        return await self.execute_powershell(script)

    # ------------------------------------------------------------------
    # 密码策略与强密码生成
    # ------------------------------------------------------------------
    async def get_password_policy(self) -> dict:
        """通过 secedit 导出并解析密码策略。

        返回字典包含: ``minimum_length`` / ``complexity_required`` /
        ``history_size`` / ``max_age_days`` / ``min_age_days``。
        结果会缓存到 ``self._cached_policy``，供同步方法
        :meth:`generate_strong_password` 使用。
        """
        if self.demo:
            self._cached_policy = dict(DEFAULT_PASSWORD_POLICY)
            return self._cached_policy

        try:
            result = await self.execute_powershell(GET_PASSWORD_POLICY_PS)
            policy: dict = {}
            if result.success:
                for raw_line in result.std_out.strip().split("\n"):
                    line = raw_line.strip()
                    if line.startswith("MinimumPasswordLength"):
                        policy["minimum_length"] = _safe_int(line, 8)
                    elif line.startswith("PasswordComplexity"):
                        policy["complexity_required"] = bool(_safe_int(line, 1))
                    elif line.startswith("PasswordHistorySize"):
                        policy["history_size"] = _safe_int(line, 0)
                    elif line.startswith("MaximumPasswordAge"):
                        policy["max_age_days"] = _safe_int(line, 42)
                    elif line.startswith("MinimumPasswordAge"):
                        policy["min_age_days"] = _safe_int(line, 1)
            # 补全默认值
            for key, value in DEFAULT_PASSWORD_POLICY.items():
                policy.setdefault(key, value)
            self._cached_policy = policy
            logger.info("获取密码策略成功: %s", policy)
            return policy
        except Exception as e:  # noqa: BLE001
            logger.error("获取密码策略失败: %s", e)
            self._cached_policy = dict(DEFAULT_PASSWORD_POLICY)
            return self._cached_policy

    def generate_strong_password(self, length: int = 16) -> str:
        """根据密码策略生成强密码（同步，纯计算）。

        使用 ``self._cached_policy``（由 :meth:`get_password_policy` 缓存），
        若未缓存则使用默认策略。复杂度要求开启时，保证至少包含大写字母、
        小写字母、数字与特殊字符各一个。
        """
        policy = self._cached_policy or DEFAULT_PASSWORD_POLICY
        min_len = policy.get("minimum_length", 8)
        complexity = policy.get("complexity_required", True)

        actual_length = max(length, min_len)

        if complexity:
            uppercase = secrets.choice(string.ascii_uppercase)
            lowercase = secrets.choice(string.ascii_lowercase)
            digit = secrets.choice(string.digits)
            special = secrets.choice("!@#$%^&*()_+-=[]{}|;:,.<>?")
            remaining = max(0, actual_length - 4)
            alphabet = (
                string.ascii_letters
                + string.digits
                + "!@#$%^&*()_+-=[]{}|;:,.<>?"
            )
            rest = "".join(secrets.choice(alphabet) for _ in range(remaining))
            chars = list(uppercase + lowercase + digit + special + rest)
            secrets.SystemRandom().shuffle(chars)
            password = "".join(chars)
        else:
            alphabet = string.ascii_letters + string.digits
            password = "".join(
                secrets.choice(alphabet) for _ in range(actual_length)
            )

        logger.info("生成强密码完成，长度: %d", len(password))
        return password

    # ------------------------------------------------------------------
    # 生命周期管理
    # ------------------------------------------------------------------
    async def close(self):
        """关闭底层 transport 的 aiohttp session。"""
        await self._transport.close()

    async def __aenter__(self) -> "AsyncWinRMClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()
