# 01 - 铁律（违反 = 严重错误）

这些规则**不可违反**。违反会导致性能退化、安全漏洞或架构腐化。

## 命令执行

### 1. 禁止同步阻塞调用出现在异步上下文

```python
# ✗ 禁止：在 async 函数中调用同步阻塞 IO
async def bad_handler():
    time.sleep(1)                    # 阻塞事件循环
    requests.get("https://...")      # 同步 HTTP

# ✓ 正确
async def good_handler():
    await asyncio.sleep(1)
    async with aiohttp.ClientSession() as s:
        await s.get("https://...")
```

详见 `02-async-patterns.md`。

## 架构

### 2. 禁止重新引入 Django

本项目已从 Django 全量重写为 FastAPI 异步架构。**禁止**：
- 引入 `django`、`django-admin`、`django-bootstrap5` 等 Django 包
- 用 Django ORM 替代 SQLAlchemy
- 用 Django 模板替代 Jinja2/JinjaX

### 3. 禁止用同步 WinRM 库

```python
# ✗ 禁止
from winrm import Protocol

# ✓ 正确
from app.winrm.client import WinRMClient
```

### 4. 禁止移除或绕过站点隔离

所有业务数据查询**必须**按 `site_group_id` 过滤。详见 `05-tenant.md`。

## 安全

### 5. 禁止明文存储密码

密码哈希链路：**前端 BLAKE2b 预哈希 → 后端 Argon2id 加盐慢哈希**。

### 6. 禁止在 App Shell 缓存中包含用户状态

App Shell 缓存的 HTML **不得**包含：用户名、用户 ID、token、个性化数据、`Set-Cookie` 头。
违反会导致跨用户数据泄漏。详见 `04-caching.md`。

### 7. 生产环境必须显式配置所有密钥

开发模式（`DEBUG=1` 或 `2C2A_DEMO=1`）允许从 `SECRET_KEY` 自动派生，生产**禁止**。
生成密钥：`2c2a keys generate`。

## 前端

### 8. 禁止 CDN 链接

所有前端资源**必须**下载到 `app/static/vendor/` 本地服务。

### 9. 禁止内联样式（.design 体系例外）

遗留 `base.css` 体系：样式统一放 `app/static/css/base.css`。

**例外**：`.design` 体系使用内联 `style` 与 CSS 变量（`--vercel-*` / `--c-*`）承载主题 token，主题 token 集中在布局模板的 `<style id="theme-vars">` 中。详见 `09-frontend.md`。

## Git

### 10. 禁止 force push 到 main/master

功能分支可 force push，main/master 禁止。

### 11. feat/* 和 hotfix/* 分支合并后立即删除

## 迁移

### 12. 禁止 `SeparateDatabaseAndState` 空操作

```python
# ✗ 禁止
def upgrade():
    pass
```

## 提交

### 13. 未经用户明确要求不得提交

**只有用户明确说"提交"/"commit"时才执行 git commit**。