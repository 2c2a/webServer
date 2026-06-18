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
                auth=self._build_auth(),
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
    ) -> str:
        """构造 WS-Management SOAP envelope。

        :param action: WS-Addressing Action URI
        :param resource_uri: WS-Management 资源 URI
        :param selectors: 选择器集合（如 ``{"ShellId": "..."}``），
                          用于定位具体资源实例
        :param body: 内层 SOAP Body 的 XML 片段（已由调用方构造）
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

        message_id = f"uuid:{uuid.uuid4()}"

        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<s:Envelope xmlns:s="{NS['s']}" xmlns:wsa="{NS['wsa']}" xmlns:wsman="{NS['wsman']}" xmlns:rsp="{NS['rsp']}">
  <s:Header>
    <wsa:Action s:mustUnderstand="true">{xml_escape(action)}</wsa:Action>
    <wsa:To>{xml_escape(self.endpoint)}</wsa:To>
    <wsman:ResourceURI s:mustUnderstand="true">{xml_escape(resource_uri)}</wsman:ResourceURI>
    {selector_set}
    <wsa:MessageID>{message_id}</wsa:MessageID>
    <wsa:ReplyTo>
      <wsa:Address>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</wsa:Address>
    </wsa:ReplyTo>
  </s:Header>
  <s:Body>{body}</s:Body>
</s:Envelope>"""
        return envelope

    # ------------------------------------------------------------------
    # 发送请求（带重试 + 指数退避）
    # ------------------------------------------------------------------
    async def post(self, body: str) -> str:
        """发送 SOAP 请求，返回响应体文本。

        带最大 ``max_retries`` 次重试与指数退避（1s, 2s, 4s ...），
        退避使用 ``asyncio.sleep``，绝不阻塞事件循环。

        - HTTP 200：返回响应体
        - HTTP 5xx：触发重试
        - HTTP 4xx 等其他状态：返回响应体（含错误信息），由调用方解析
        """
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
