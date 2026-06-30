# 11 - WinRM 异步客户端

## 架构

```
app/winrm/
├── transport.py    # 底层 aiohttp WS-Management 传输
├── client.py       # 高层异步客户端
└── commands.py     # PowerShell 命令模板 + 转义
```

基于 `aiohttp`，**全异步**。替代同步 `winrm` 库。

## 使用

```python
from app.winrm.client import WinRMClient

client = WinRMClient(
    host="192.168.1.100",
    username="administrator",
    password="...",
    port=5985,
    timeout=30,
)

result = await client.execute_command("whoami")
await client.create_user("alice", "P@ssw0rd!")
users = await client.list_users()
```

## 命令注入防护

用 `commands.py` 中的模板 + `escape_ps_string`，禁止拼接：

```python
# ✗ 禁止
cmd = f"net user {username} {password} /add"

# ✓ 正确
from app.winrm.commands import CREATE_USER_PS, escape_ps_string
cmd = CREATE_USER_PS.format(name=escape_ps_string(username), password=escape_ps_string(password))
```

## demo 模式

`2C2A_DEMO=1` 时所有 `execute_*` 返回模拟成功结果。

## 后台任务

长 WinRM 操作放 RedisHuey 任务：

```bash
2c2a serve worker
```

## 禁止

1. 禁止用同步 winrm 库
2. 禁止在 async 中阻塞执行 WinRM 操作
3. 禁止拼接 PowerShell 命令
4. 禁止在 HTTP 请求中直接执行长 WinRM 操作（用 Huey 任务）