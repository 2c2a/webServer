"""异步 WinRM 客户端包。

基于 aiohttp 实现的异步 WS-Management 客户端，替代同步 pywinrm。

典型用法::

    from app.winrm import AsyncWinRMClient

    async with AsyncWinRMClient(
        "10.0.0.1", username="admin", password="***"
    ) as client:
        result = await client.execute_command("whoami")
        if result.success:
            print(result.std_out)

或从 Host 模型构造::

    client = await AsyncWinRMClient.from_host_config(host)
    try:
        await client.create_user("alice", "P@ssw0rd!")
    finally:
        await client.close()
"""
from app.winrm.client import AsyncWinRMClient, CommandInjectionError, WinRMResult

__all__ = ["AsyncWinRMClient", "WinRMResult", "CommandInjectionError"]
