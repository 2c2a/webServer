# 04 - 缓存策略

## 核心理念：App Shell + HTMX 片段分离

```
┌─────────────────────────────────────────────────────┐
│  App Shell（可被 CDN 全量缓存）                       │
│  ── 仅含租户级配置：站点名、主题、ICP                  │
│  ── 绝不含用户状态                                    │
│  ── 缓存键：keyed-BLAKE2b(domain + path)             │
├─────────────────────────────────────────────────────┤
│  HTMX 动态片段（不可缓存）                            │
│  ── 页面加载后 HTMX 独立请求                          │
│  ── 基于用户状态实时返回                              │
└─────────────────────────────────────────────────────┘
```

## App Shell 缓存

可缓存条件：
1. 仅依据请求域名解析租户配置渲染
2. 不依赖用户登录状态
3. 不含 `Set-Cookie` 头
4. 不含任何用户特定数据

```python
from app.cache.app_shell import get_app_shell_cache, set_app_shell_cache

html = await get_app_shell_cache(domain, path)
if html:
    return HTMLResponse(html, headers=edge_cache_headers())

html = render_template("layouts/app_shell.html", **ctx)
await set_app_shell_cache(domain, path, html)
return HTMLResponse(html, headers=edge_cache_headers())
```

缓存键：`shell:{domain_hash}:{path_hash}`（keyed-BLAKE2b 短哈希）

## HTMX 片段缓存

默认不缓存（`fragment_cache_ttl=0`）。仅当片段内容与用户无关时才可缓存。

## 缓存键命名规范

| 前缀 | 用途 |
| --- | --- |
| `shell:` | App Shell 边缘缓存 |
| `frag:` | HTMX 片段缓存 |
| `tenant:` | 租户配置缓存 |

## 禁止

1. 禁止在 App Shell 缓存中包含用户状态
2. 禁止用用户 ID 作为缓存键
3. 禁止缓存含敏感数据的片段