# 02 - 异步模式

本项目全异步。**任何阻塞事件循环的代码都是 bug**。

## 数据库访问

### 会话获取

```python
from app.core.db import get_db

# ✓ Web 路由用依赖注入
@router.get("/users/{id}")
async def get_user(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == id))
    return result.scalar_one_or_none()
```

```python
# ✓ CLI / 后台任务用上下文管理器
from app.cli.utils import db_session

async def _do():
    async with db_session() as session:
        result = await session.execute(select(User))
        return result.scalars().all()
```

### 查询必须 await

```python
# ✗ 错误
result = db.execute(select(User))          # 返回协程

# ✓ 正确
result = await db.execute(select(User))
users = (await db.execute(select(User))).scalars().all()
```

### 关系加载

异步会话关闭后不能懒加载关系，会触发 `DetachedInstanceError`。**必须**用 `selectinload` 预加载。

```python
from sqlalchemy.orm import selectinload

async def get_user_ban(username: str):
    async with db_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.active_ban)).where(User.username == username)
        )
        user = result.scalar_one_or_none()
        ban = user.active_ban  # 已加载，安全
    return ban
```

## HTTP 调用

### 用 aiohttp，禁用 requests

```python
# ✗ 禁止
import requests

# ✓ 正确
import aiohttp
async with aiohttp.ClientSession() as s:
    async with s.get("https://...") as resp:
        return await resp.text()
```

### 连接池复用

不要在每次请求创建 `ClientSession`，在类中复用。

## 并发

### 并发执行多个独立 IO

```python
import asyncio

user, profile, settings = await asyncio.gather(
    get_user(uid),
    get_profile(uid),
    get_settings(uid),
)
```

## 常见陷阱

1. 在同步函数中调用 async → 用 `run_async`（仅 CLI）/ 改为 async
2. 忘记 await 协程 → 有 RuntimeWarning
3. 在 async 函数中用同步 DB 驱动 → 必须用异步驱动