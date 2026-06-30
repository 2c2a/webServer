"""基于 aiohttp 的 WS-Management 协议传输层。

用异步 HTTP 客户端替代同步 pywinrm 的传输层，提供：

- NTLM 认证（用户名 / 密码）
- 证书认证（客户端证书 + 私钥，通过 SSL context 加载）
- 连接池复用（``aiohttp.TCPConnector`` limit=10）
- 失败重试 + 指数退避（``asyncio.sleep``，绝不阻塞事件循环）
- WS-Management SOAP envelope 构造辅助方法

.. note::
    完整的 NTLM 握手（Type1 / Type2 / Type3 三轮协商）需要 ``pyspnego`` 或
    ``requests_ntlm`` 等库。本实现先用 ``aiohttp.BasicAuth`` 占位，保证结构完整；
    生产环境应替换为真正的 NTLM 协商。证书认证则已完整实现（SSL context 加载
    客户端证书）。
"""
from __future__ import annotations

import asyncio
import logging
import ssl
import uuid
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

import aiohttp

logger = logging.getLogger("2c2a")

# ---------------------------------------------------------------------------
# WS-Management / SOAP 命名空间
# ---------------------------------------------------------------------------
NS = {
    "s": "http://www.w3.org/2003/05/soap-envelope",  # SOAP 1.2
    "wsa": "http://schemas.xmlsoap.org/ws/2004/08/addressing",
    "wsman": "http://schemas.dmtf.org/wbem/wsman/1/wsman.xsd",
    "wxf": "http://schemas.xmlsoap.org/ws/2004/09/transfer",
    "rsp": "http://schemas.microsoft.com/wbem/wsman/1/windows/shell",
    "cfg": "http://schemas.microsoft.com/wbem/wsman/1/config",
}

# 资源 URI
RSRC_CMD = "http://schemas.microsoft.com/wbem/wsman/1/windows/shell/cmd"
RSRC_PS = "http://schemas.microsoft.com/powershell/Microsoft.PowerShell"

# 常用 WS-Addressing Action
ACTION_CREATE = "http://schemas.xmlsoap.org/ws/2004/09/transfer/Create"
ACTION_COMMAND = "http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Command"
ACTION_RECEIVE = "http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Receive"
ACTION_SIGNAL = "http://schemas.microsoft.com/wbem/wsman/1/windows/shell/Signal"
ACTION_DELETE = "http://schemas.xmlsoap.org/ws/2004/09/transfer/Delete"

# 终止信号码
SIGNAL_TERMINATE = (
    "http://schemas.microsoft.com/wbem/wsman/1/windows/shell/signal/terminate"
)


class WinRMTransportError(Exception):
    """WS-Management 传输层错误。"""


class WinRMTransport:
    """WS-Management 协议异步传输层。

    封装 aiohttp 的会话管理、认证、SOAP envelope 构造与重试逻辑，
    供 :class:`app.winrm.client.AsyncWinRMClient` 调用。
    """

    def __init__(
        self,
        endpoint: str,
        auth: dict,
        timeout: int = 30,
        max_retries: int = 3,
        use_ssl: bool = False,
        verify_ssl: bool = True,
    ):
        """
        :param endpoint: WS-Management 端点，形如 ``http://host:5985/wsman``
        :param auth: 认证信息字典：

            * NTLM: ``{"method": "ntlm", "username": "...", "password": "..."}``
            * 证书: ``{"method": "certificate",
                       "cert_pem_path": "...", "key_pem_path": "...",
                       "username": "..."(可选)}``
        :param timeout: 单次请求总超时（秒）
        :param max_retries: 失败最大重试次数
        :param use_ssl: 是否使用 SSL（影响 ssl context 构造）
        :param verify_ssl: 是否校验服务器证书
        """
        self.endpoint = endpoint
        self.auth = auth
        self.timeout = timeout
        self.max_retries = max_retries
        self.use_ssl = use_ssl
        self.verify_ssl = verify_ssl

        # aiohttp 会话（懒加载，避免在事件循环外创建）
        self._session: Optional[aiohttp.ClientSession] = None
        # 预构造 SSL 上下文（证书认证 / 服务器证书校验）
        self._ssl_context: Optional[ssl.SSLContext] = self._build_ssl_context()

    # ------------------------------------------------------------------
    # SSL / 认证相关
    # ------------------------------------------------------------------
    def _build_ssl_context(self) -> Optional[ssl.SSLContext]:
        """构造 SSL 上下文。

        - 证书认证：加载客户端证书与私钥（强制 SSL）
        - ``verify_ssl=False``：关闭服务器证书校验（仅用于内网 / 自签场景）
        - 非 SSL 的 NTLM：返回 None，由 aiohttp 自行处理
        """
        method = self.auth.get("method")
        if not self.use_ssl and method != "certificate":
            return None

        ctx = ssl.create_default_context()
        if not self.verify_ssl:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

        if method == "certificate":
            cert_pem = self.auth.get("cert_pem_path")
            key_pem = self.auth.get("key_pem_path")
            if not cert_pem or not key_pem:
                raise ValueError("证书认证必须提供 cert_pem_path 与 key_pem_path")
            ctx.load_cert_chain(certfile=cert_pem, keyfile=key_pem)
        return ctx

    def _build_auth(self) -> Optional[aiohttp.BasicAuth]:
        """构造 aiohttp 认证对象。

        NTLM 完整握手需要 ``pyspnego``；此处先用 ``BasicAuth`` 占位，
        保证结构完整。生产环境应替换为真正的 NTLM 协商（见模块文档）。
        """
        method = self.auth.get("method")
        if method == "ntlm":
            username = self.auth.get("username", "")
            password = self.auth.get("password", "")
            # 占位：实际 NTLM 需 Type1/2/3 多轮协商
            return aiohttp.BasicAuth(username, password)
        # 证书认证依赖 SSL context，不需要 BasicAuth
        return None

    # ------------------------------------------------------------------
    # Session 管理（懒加载 + 连接池复用）
    # ------------------------------------------------------------------
    async def _get_session(self) -> aiohttp.ClientSession:
        """懒加载 ``aiohttp.ClientSession``，连接池 limit=10。

        会话在首次请求时创建并复用，避免每次请求新建连接。
        若会话已关闭则重建。
        """
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=10,  # 连接池上限
                limit_per_host=10,
                ssl=self._ssl_context,
            )
            client_timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=client_timeout,
                headers={"Content-Type": "application/soap+xml;charset=UTF-8"},
            )
        return self._session

    # ------------------------------------------------------------------
    # SOAP Envelope 构造
    # ------------------------------------------------------------------
    def _build_envelope(
        self,
        action: str,
        resource_uri: str,
        selectors: Optional[dict] = None,
        body: str = "",
        option_set: Optional[dict] = None,
    ) -> str:
        """构造 WS-Management SOAP envelope。

        :param action: WS-Addressing Action URI
        :param resource_uri: WS-Management 资源 URI
        :param selectors: 选择器集合（如 ``{"ShellId": "..."}``），
                          用于定位具体资源实例
        :param body: 内层 SOAP Body 的 XML 片段（已由调用方构造）
        :param option_set: WS-Management OptionSet（如 ``{"WINRS_NOPROFILE": "FALSE"}``），
                           Command action 必须提供
        :returns: 完整的 SOAP envelope 字符串

        所有外部输入均经过 :func:`xml.sax.saxutils.escape`，避免 XML 注入。
        """
        # 构造选择器集合节点
        selector_set = ""
        if selectors:
            sel_items = "".join(
                f'<wsman:Selector Name="{xml_escape(name)}">'
                f"{xml_escape(str(value))}</wsman:Selector>"
                for name, value in selectors.items()
            )
            selector_set = f"<wsman:SelectorSet>{sel_items}</wsman:SelectorSet>"

        # 构造 OptionSet 节点（Command action 必需）
        option_set_xml = ""
        if option_set:
            opt_items = "".join(
                f'<wsman:Option Name="{xml_escape(name)}">'
                f"{xml_escape(str(value))}</wsman:Option>"
                for name, value in option_set.items()
            )
            option_set_xml = f"<wsman:OptionSet>{opt_items}</wsman:OptionSet>"

        message_id = f"uuid:{uuid.uuid4()}"

        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{NS['s']}" xmlns:wsa="{NS['wsa']}" xmlns:wsman="{NS['wsman']}" xmlns:rsp="{NS['rsp']}">
  <s:Header>
    <wsa:Action s:mustUnderstand="true">{xml_escape(action)}</wsa:Action>
    <wsa:To>{xml_escape(self.endpoint)}</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">{xml_escape(resource_uri)}</wsman:ResourceURI>
    {selector_set}
    {option_set_xml}
    <wsa:MessageID>{message_id}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
  </s:Header>
  <s:Body>{body}</s:Body>
</s:Envelope>"""
        return envelope

    # ------------------------------------------------------------------
    # NTLM 认证辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_ntlm_challenge(www_auth_headers: list[str]) -> bytes:
        """从 WWW-Authenticate 头列表中提取 NTLM/Negotiate challenge token。"""
        import base64

        logger.info("WWW-Authenticate headers: %s", www_auth_headers)
        for header in www_auth_headers:
            for scheme in header.split(","):
                scheme = scheme.strip()
                for prefix in ("NTLM ", "NEGOTIATE "):
                    if scheme.upper().startswith(prefix):
                        token = scheme[len(prefix):].strip()
                        return base64.b64decode(token.encode())
        raise WinRMTransportError(
            f"服务器 401 响应中未找到 NTLM/Negotiate challenge: {www_auth_headers}"
        )

    @staticmethod
    def _select_auth_scheme(auth_headers: list[str]) -> str:
        """根据 401 响应头选择 Negotiate 或 NTLM scheme。"""
        for header in auth_headers:
            for part in header.split(","):
                part = part.strip()
                if part.upper().startswith("NEGOTIATE"):
                    return "Negotiate"
        return "NTLM"

    async def _post_with_ntlm(self, body: str, auth_headers: list[str] | None = None) -> str:
        """手动完成 NTLM Type1/Type2/Type3 三轮协商后发送 SOAP 请求。

        NTLM 认证上下文绑定 TCP 连接，因此 Type1 与 Type3 必须复用同一连接。
        本方法使用独立的单连接 aiohttp 会话完成完整握手，避免连接池复用导致
        Type3 走到新连接而认证失败。
        """
        import base64

        import spnego

        scheme = self._select_auth_scheme(auth_headers) if auth_headers else "Negotiate"
        target = self.endpoint.split("://", 1)[-1].split("/", 1)[0]
        hostname = target.split(":", 1)[0]
        username = self.auth.get("username", "")
        password = self.auth.get("password", "")
        client = spnego.client(
            username,
            password,
            protocol="negotiate",
            hostname=hostname,
            service="http",
        )

        # 独立单连接会话：保证 Type1/Type3 复用同一 TCP 连接
        # force_close=False 让连接在 Type1 响应后保持打开，供 Type3 使用
        ntlm_connector = aiohttp.TCPConnector(
            limit=1,
            limit_per_host=1,
            ssl=self._ssl_context,
            force_close=False,
        )
        ntlm_timeout = aiohttp.ClientTimeout(total=self.timeout)
        ntlm_session = aiohttp.ClientSession(
            connector=ntlm_connector,
            timeout=ntlm_timeout,
            headers={"Content-Type": "application/soap+xml;charset=UTF-8"},
        )

        headers = {
            "Content-Type": "application/soap+xml;charset=UTF-8",
        }

        try:
            # Type 1: negotiate（不关闭连接，供 Type3 复用）
            negotiate = base64.b64encode(client.step() or b"").decode()
            async with ntlm_session.post(
                self.endpoint,
                data=body.encode("utf-8"),
                headers={**headers, "Authorization": f"{scheme} {negotiate}"},
            ) as resp:
                logger.info("NTLM Type1 response status: %s", resp.status)
                if resp.status == 200:
                    return await resp.text()
                if resp.status != 401:
                    text = await resp.text()
                    logger.warning("NTLM Type1 返回非 401: status=%s body=%s", resp.status, text[:200])
                    return text
                challenge = self._extract_ntlm_challenge(resp.headers.getall("WWW-Authenticate"))

            # Type 3: authenticate（复用同一 TCP 连接）
            authenticate = base64.b64encode(client.step(challenge) or b"").decode()
            async with ntlm_session.post(
                self.endpoint,
                data=body.encode("utf-8"),
                headers={**headers, "Authorization": f"{scheme} {authenticate}"},
            ) as resp:
                text = await resp.text()
                logger.info("NTLM Type3 response status: %s body=%s", resp.status, text[:200])
                if resp.status == 200:
                    return text
                if resp.status == 401:
                    raise WinRMTransportError("NTLM 认证失败，请检查用户名/密码")
                return text
        finally:
            await ntlm_session.close()

    # ------------------------------------------------------------------
    # 发送请求（带重试 + 指数退避）
    # ------------------------------------------------------------------
    async def post(self, body: str) -> str:
        """发送 SOAP 请求，返回响应体文本。

        带最大 ``max_retries`` 次重试与指数退避（1s, 2s, 4s ...），
        退避使用 ``asyncio.sleep``，绝不阻塞事件循环。

        - NTLM 认证：每次请求都走完整 NTLM 握手
        - HTTP 200：返回响应体
        - HTTP 5xx：触发重试
        - HTTP 4xx 等其他状态：返回响应体（含错误信息），由调用方解析
        """
        # NTLM 模式：每次请求都重新协商，避免连接复用导致 500
        if self.auth.get("method") == "ntlm":
            return await self._post_with_ntlm(body)

        last_exc: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                session = await self._get_session()
                async with session.post(
                    self.endpoint,
                    data=body.encode("utf-8"),
                    headers={
                        "Content-Type": "application/soap+xml;charset=UTF-8",
                    },
                ) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        return text
                    if (
                        resp.status == 401
                        and self.auth.get("method") == "ntlm"
                    ):
                        auth_headers = resp.headers.getall("WWW-Authenticate")
                        return await self._post_with_ntlm(body, auth_headers)
                    # 5xx 视为可重试错误
                    if 500 <= resp.status < 600:
                        raise aiohttp.ClientResponseError(
                            resp.request_info,
                            resp.history,
                            status=resp.status,
                            message=f"WS-Management 服务端错误: {resp.status}",
                        )
                    # 4xx 等不可重试错误，返回响应体供调用方解析
                    logger.warning(
                        "WS-Management 请求返回非 200: status=%s", resp.status
                    )
                    return text
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exc = e
                logger.warning(
                    "WS-Management 请求失败 (尝试 %d/%d): %s",
                    attempt + 1,
                    self.max_retries,
                    e,
                )
                if attempt < self.max_retries - 1:
                    # 指数退避：1s, 2s, 4s ...
                    backoff = 2 ** attempt
                    await asyncio.sleep(backoff)

        # 所有重试均失败
        raise WinRMTransportError(
            f"WS-Management 请求在 {self.max_retries} 次重试后仍失败: {last_exc}"
        )

    async def close(self):
        """关闭 aiohttp session，释放连接池资源。"""
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None
