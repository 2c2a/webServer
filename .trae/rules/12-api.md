# 12 - API 路由

## 路由类型

| 类型 | 前缀 | 返回 | 用途 |
| --- | --- | --- | --- |
| REST API | `/api/v1/` | JSON | 前端/客户端 |
| 认证 API | `/auth/` | JSON | 登录/注册/刷新 |
| Web 页面 | `/` | HTML | App Shell（可缓存） |
| HTMX 片段 | `/fragments/` | HTML | 动态片段（不可缓存） |
| 插件路由 | `/<plugin_id>/` | JSON/HTML | 插件 |

## 依赖注入

```python
from app.core.db import get_db
from app.tenant.dependencies import get_tenant
from app.auth.dependencies import get_current_user, require_staff

@router.get("/hosts")
async def list_hosts(
    tenant: TenantContext = Depends(get_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await db.execute(
        select(Host).where(Host.site_group_id == tenant.site_group_id)
    ).scalars().all()

@router.delete("/hosts/{id}")
async def delete_host(
    id: int,
    user: CurrentUser = Depends(require_staff),
    db: AsyncSession = Depends(get_db),
):
    ...
```

## REST API 规范

```python
router = APIRouter(prefix="/api/v1/hosts", tags=["hosts"])

@router.get("")              # 列表
@router.get("/{id}")         # 详情
@router.post("")             # 创建
@router.put("/{id}")         # 全量更新
@router.patch("/{id}")       # 部分更新
@router.delete("/{id}")      # 删除
```

### Pydantic Schema

```python
class HostOut(BaseModel):
    id: int
    name: str
    ip: str
    model_config = {"from_attributes": True}
```

## 认证 API

```python
@router.post("/login")    # 登录 → 签发 JWT + Refresh Cookie
@router.post("/refresh")  # 刷新 → 签发新 JWT
@router.post("/logout")   # 登出 → 删除 Cookie
```

## 异常处理

```python
from app.core.exceptions import AuthError, NotFoundError

@router.get("/hosts/{id}")
async def get_host(id: int, db = Depends(get_db)):
    host = await db.get(Host, id)
    if not host:
        raise NotFoundError("主机不存在")
    return host
```

## 禁止

1. 禁止跨租户查询
2. 禁止在 App Shell 路由依赖用户
3. 禁止返回明文密码或哈希