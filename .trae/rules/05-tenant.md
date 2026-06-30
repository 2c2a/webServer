# 05 - 租户隔离

## 核心模型

```
SiteGroup（站点组）
├── id, slug, site_name, is_active
├── config (SiteGroupConfig)
├── hostnames (SiteGroupHostname[])
└── admins (User[])
```

所有业务模型混入 `SiteGroupMixin`，带 `site_group_id` 字段。

## 域名解析

```
请求 → TenantMiddleware（提取 Host 头）
     → resolve_tenant_by_hostname(db, hostname)
        ├─ Redis 缓存命中 → 返回 SiteGroup
        └─ 查 SiteGroupHostname 表 → 返回 SiteGroup
           └─ 未匹配 → 回退默认租户
     → 注入 TenantContext 到 request.state
```

```python
from app.tenant.dependencies import get_tenant

@router.get("/")
async def page(tenant: TenantContext = Depends(get_tenant)):
    # tenant.site_group_id  ← 当前租户
    ...
```

## 数据隔离规则

### 所有业务查询必须按 site_group_id 过滤

```python
# ✗ 禁止：跨租户查询
hosts = await db.execute(select(Host))

# ✓ 正确
hosts = await db.execute(
    select(Host).where(Host.site_group_id == tenant.site_group_id)
)
```

### 新建记录必须带 site_group_id

```python
host = Host(name="web-01", site_group_id=tenant.site_group_id, ...)
```

### slug 生成

非 ASCII 名称无法生成有效 slug 时用随机串兜底：`f"site-{secrets.token_hex(4)}"`

## CLI 管理

```bash
2c2a tenant list
2c2a tenant create "我的站点" --slug my-site
2c2a tenant add-hostname my-site example.com
2c2a tenant add-admin my-site admin
2c2a tenant invalidate-cache
```

## 禁止

1. 禁止跨租户查询
2. 禁止在 App Shell 渲染时依赖用户
3. 禁止硬编码 site_group_id