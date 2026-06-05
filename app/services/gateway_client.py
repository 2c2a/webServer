"""
Gateway 客户端服务

通过 HTTP 与网关通信，管理隧道连接和 RDP 会话。
提供同步和异步两种接口。
"""
import logging
from typing import Any, Optional

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)


class GatewayError(Exception):
    """网关操作异常"""
    pass


class GatewayClient:
    """
    网关客户端

    通过 HTTP API 与网关服务通信，支持：
    - 隧道管理（踢出、统计）
    - RDP 会话管理
    - 远程命令执行
    - PAA 令牌签发
    - RDP 文件生成
    """

    def __init__(self):
        settings = get_settings()
        self._gateway_address = settings.gateway_address
        self._gateway_port = settings.gateway_port
        self._control_socket = settings.gateway_control_socket
        self._paa_signing_key = settings.gateway_paa_token_signing_key
        self._paa_token_expiry = settings.gateway_paa_token_expiry_seconds
        self._enabled = settings.gateway_enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def gateway_url(self) -> str:
        return f"https://{self._gateway_address}:{self._gateway_port}"

    # ========== 同步方法（Huey 任务使用）==========

    def remote_exec_sync(
        self,
        token: str,
        script: str,
    ) -> Optional[dict]:
        """同步执行远程脚本（Huey 任务使用）"""
        if not self._enabled:
            logger.warning("网关未启用，无法执行远程命令")
            return None

        try:
            with httpx.Client(verify=False, timeout=30) as client:
                response = client.post(
                    f"{self.gateway_url}/api/tunnel/{token}/exec",
                    json={"script": script},
                )
                if response.status_code == 200:
                    return response.json()
                logger.error("远程执行失败: HTTP %s", response.status_code)
                return None
        except httpx.HTTPError as e:
            logger.error("远程执行HTTP请求失败: %s", str(e))
            return None

    def tunnel_kick_sync(self, token: str) -> bool:
        """同步踢出隧道连接"""
        if not self._enabled:
            return False
        try:
            with httpx.Client(verify=False, timeout=10) as client:
                response = client.post(
                    f"{self.gateway_url}/api/tunnel/{token}/kick",
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    def tunnel_stats_sync(self, token: Optional[str] = None) -> Optional[Any]:
        """同步获取隧道统计信息"""
        if not self._enabled:
            return None
        try:
            with httpx.Client(verify=False, timeout=10) as client:
                url = f"{self.gateway_url}/api/tunnel/stats"
                if token:
                    url += f"?token={token}"
                response = client.get(url)
                if response.status_code == 200:
                    return response.json()
                return None
        except httpx.HTTPError:
            return None

    def rdp_session_stats_sync(self) -> Optional[Any]:
        """同步获取 RDP 会话统计"""
        if not self._enabled:
            return None
        try:
            with httpx.Client(verify=False, timeout=10) as client:
                response = client.get(f"{self.gateway_url}/api/rdp/sessions")
                if response.status_code == 200:
                    return response.json()
                return None
        except httpx.HTTPError:
            return None

    def rdp_session_kick_sync(self, session_id: str) -> bool:
        """同步踢出 RDP 会话"""
        if not self._enabled:
            return False
        try:
            with httpx.Client(verify=False, timeout=10) as client:
                response = client.post(
                    f"{self.gateway_url}/api/rdp/sessions/{session_id}/kick",
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    # ========== 异步方法（FastAPI 路由使用）==========

    async def remote_exec(
        self,
        token: str,
        script: str,
    ) -> Optional[dict]:
        """异步执行远程脚本"""
        if not self._enabled:
            logger.warning("网关未启用，无法执行远程命令")
            return None

        try:
            async with httpx.AsyncClient(verify=False, timeout=30) as client:
                response = await client.post(
                    f"{self.gateway_url}/api/tunnel/{token}/exec",
                    json={"script": script},
                )
                if response.status_code == 200:
                    return response.json()
                logger.error("远程执行失败: HTTP %s", response.status_code)
                return None
        except httpx.HTTPError as e:
            logger.error("远程执行HTTP请求失败: %s", str(e))
            return None

    async def tunnel_kick(self, token: str) -> bool:
        """异步踢出隧道连接"""
        if not self._enabled:
            return False
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                response = await client.post(
                    f"{self.gateway_url}/api/tunnel/{token}/kick",
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def tunnel_stats(self, token: Optional[str] = None) -> Optional[Any]:
        """异步获取隧道统计信息"""
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                url = f"{self.gateway_url}/api/tunnel/stats"
                if token:
                    url += f"?token={token}"
                response = await client.get(url)
                if response.status_code == 200:
                    return response.json()
                return None
        except httpx.HTTPError:
            return None

    async def rdp_session_stats(self) -> Optional[Any]:
        """异步获取 RDP 会话统计"""
        if not self._enabled:
            return None
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                response = await client.get(f"{self.gateway_url}/api/rdp/sessions")
                if response.status_code == 200:
                    return response.json()
                return None
        except httpx.HTTPError:
            return None

    async def rdp_session_kick(self, session_id: str) -> bool:
        """异步踢出 RDP 会话"""
        if not self._enabled:
            return False
        try:
            async with httpx.AsyncClient(verify=False, timeout=10) as client:
                response = await client.post(
                    f"{self.gateway_url}/api/rdp/sessions/{session_id}/kick",
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False

    # ========== PAA 令牌与 RDP 文件 ==========

    def generate_rdp_file(
        self,
        gateway_address: Optional[str] = None,
        gateway_port: Optional[int] = None,
        user_email: str = "",
        paa_token: str = "",
        enable_clipboard: bool = True,
        enable_printers: bool = True,
        enable_drive: bool = True,
        enable_port: bool = False,
        enable_pnp: bool = False,
    ) -> str:
        """生成 RDP 连接文件内容"""
        addr = gateway_address or self._gateway_address
        port = gateway_port or self._gateway_port

        rdp_lines = [
            "full address:s:2c2a://gateway",
            f"server port:i:{port}",
            f"gatewayhostname:s:{addr}",
            f"gatewayaccesstoken:s:{paa_token}",
            "gatewayusagemethod:i:1",
            "gatewayprofileusagemethod:i:1",
            "promptcredentialonce:i:1",
            "username:s:",
            f"alternate shell:s:{user_email}",
            "redirectclipboard:i:1" if enable_clipboard else "redirectclipboard:i:0",
            "redirectprinters:i:1" if enable_printers else "redirectprinters:i:0",
            "redirectcomports:i:0",
            "redirectsmartcards:i:0",
            "drivestoredirect:s:*" if enable_drive else "drivestoredirect:s:",
            "redirectposdevices:i:1" if enable_pnp else "redirectposdevices:i:0",
            "redirectport:i:1" if enable_port else "redirectport:i:0",
            "audiocapturemode:i:0",
            "videoplaybackmode:i:1",
            "audiomode:i:0",
            "networkautodetect:i:1",
            "bandwidthautodetect:i:1",
            "connection type:i:7",
            "compression:i:1",
            "displayconnectionbar:i:1",
            "enableworkspacereconnect:i:0",
            "disable wallpaper:i:0",
            "allow font smoothing:i:1",
            "allow desktop composition:i:1",
            "disable full window drag:i:0",
            "disable menu anims:i:0",
            "disable themes:i:0",
            "disable cursor setting:i:0",
            "bitmapcachepersistenable:i:1",
            "audiomode:i:0",
            "screen mode id:i:2",
            "use multimon:i:0",
            "desktopwidth:i:0",
            "desktopheight:i:0",
            "session bpp:i:32",
        ]
        return "\r\n".join(rdp_lines)


def is_gateway_enabled() -> bool:
    """检查网关是否启用"""
    settings = get_settings()
    return settings.gateway_enabled
