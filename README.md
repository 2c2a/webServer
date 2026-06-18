<div align="center">

![2c2a Logo](./docs/images/logo.svg)

<h1>2c2a - Cloudy Computer Account Activation Integration Platform</h1>

<p>
  <strong>异步架构重写版 · 全异步非阻塞 · 边缘缓存 · 站点隔离 · 插件系统</strong><br>
  Granian + FastAPI + SQLAlchemy 2.0 Async + HTMX OOB + RedisHuey + JinjaX + aiohttp
</p>

<p>
  <img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0%20Async-D71F00?logo=sqlalchemy&logoColor=white" alt="SQLAlchemy 2.0">
  <img src="https://img.shields.io/badge/Granian-ASGI-000" alt="Granian">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-blue.svg" alt="License: AGPL-3.0">
</p>

</div>

---

## 架构概览

2c2a v2.0 是从 Django 同步架构全面重写的异步版本，贯彻**异步化**与**模块化**思想，前端绝不阻塞。

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| ASGI 服务器 | **Granian** | Rust 内核高性能 ASGI 服务器 |
| Web 框架 | **FastAPI** | 原生异步，依赖注入 |
| ORM | **SQLAlchemy 2.0 Async** | `Mapped`/`mapped_column` 新语法，全异步会话 |
| 模板 | **JinjaX + Jinja2** | 组件化模板，配合 HTMX OOB |
| 前端交互 | **HTMX OOB** | 服务端渲染片段，Out-of-Band swap |
| 任务队列 | **RedisHuey** | 替代 Celery，轻量异步任务 |
| 远程管理 | **aiohttp** | 替代同步 pywinrm，全异步 WinRM |
| 缓存 | **Redis** | 边缘缓存 + 租户缓存 + 任务 broker |

### 核心机制

**1. App Shell 边缘全量缓存 + HTMX 动态片段精准分离**
- 页面骨架路由仅依据请求域名解析租户配置，绝不依赖用户状态
- 按域名区分 + keyed-BLAKE2b 签名生成缓存键，CDN 边缘节点全量高速缓存与防污染
- 用户导航、统计等动态内容由 HTMX 在页面加载后发起独立请求，服务端基于 Ed25519 验签实时返回不可缓存片段

**2. 身份认证**
- Access Token：Ed25519 签名 JWT，5 分钟有效期，存放前端内存（防 XSS）
- Refresh Token：AES-GCM 加密，7 天有效期，HttpOnly Cookie（防 XSS 读取）
- 密码：前端 BLAKE2b 预哈希（防 DoS 截断）+ 后端 Argon2id 加盐慢哈希（抗 GPU/ASIC 爆破）
- ban_version 机制：JWT Payload 携带版本号，封禁时递增数据库版本，无需 Redis 黑名单实现无状态秒级令牌撤销

**3. 字段级加密**
- HKDF-SHA256 按字段名派生子密钥 + AES-256-GCM 加密，实现字段级密钥隔离与防篡改

**4. 原生插件系统**
- 插件基类、服务注册表、路由提供者、UI 扩展、事件钩子
- 启动时自动发现并加载，路由动态挂载

**5. 原生站点隔离**
- 按请求域名解析租户（SiteGroup），所有业务数据按租户过滤
- 站点组配置覆盖全局配置

### 已移除功能
- 仪表盘自定义功能（DashboardWidget / WidgetLayout）
- 隧道功能（tunnel app、Host.tunnel_* 字段、Gateway 客户端）

---

## 目录结构

```
app/
├── core/           # 配置、数据库、Redis、日志、异常
├── security/       # BLAKE2b/Argon2id/HKDF/AES-GCM/Ed25519 JWT/Refresh/ban_version
├── cache/          # keyed-BLAKE2b 缓存键、App Shell 边缘缓存、HTMX 片段
├── tenant/         # 域名租户解析、中间件、依赖注入
├── models/         # SQLAlchemy 2.0 异步模型（44 模型 / 52 表）
├── auth/           # 认证依赖、路由、schemas
├── winrm/          # aiohttp 异步 WinRM 客户端
├── tasks/          # RedisHuey 异步任务
├── plugins/        # 插件系统框架 + 示例插件
├── api/v1/         # JSON API（hosts/operations/tickets/audit）
├── web/            # App Shell 页面骨架 + HTMX 动态片段
├── templates/      # Jinja2 布局/页面/片段 + JinjaX 组件
├── static/         # CSS/JS/HTMX
└── main.py         # FastAPI 应用工厂 + Granian 入口
alembic/            # 数据库迁移
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -e .
# 或
pip install granian fastapi "sqlalchemy[asyncio]" aiosqlite redis huey aiohttp \
    argon2-cffi pyjwt cryptography pydantic-settings jinjax jinja2 structlog
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 开发模式：设置 DEBUG=true 2C2A_DEMO=1，密钥自动生成
# 生产模式：必须配置 SECRET_KEY / ED25519_* / CRYPTO_MASTER_KEY_B64 / CACHE_SIGNING_KEY
```

生成密钥：
```bash
python -c "import secrets;print('SECRET_KEY='+secrets.token_urlsafe(48))"
python -c "import base64,os;print('CRYPTO_MASTER_KEY_B64='+base64.b64encode(os.urandom(32)).decode())"
python -c "import secrets;print('CACHE_SIGNING_KEY='+secrets.token_urlsafe(32))"
python -c "
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
k=Ed25519PrivateKey.generate()
print('ED25519_PRIVATE_KEY_PEM='+k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode())
print('ED25519_PUBLIC_KEY_PEM='+k.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode())
"
```

### 3. 初始化数据库

```bash
alembic upgrade head
```

### 4. 启动服务

```bash
# 开发
granian --interface asgi --reload app.main:app --host 0.0.0.0 --port 8000

# 生产（多 worker）
granian --interface asgi --workers 4 app.main:app --host 0.0.0.0 --port 8000
```

### 5. 启动任务消费者（可选，WinRM 后台操作）

```bash
huey_consumer app.tasks.huey_app.huey
```

---

## 缓存策略详解

```
请求 → TenantMiddleware（按域名解析租户，Redis 缓存）
     → App Shell 路由（仅租户配置，keyed-BLAKE2b 缓存键）
        ├─ 缓存命中 → 返回 HTML（Cache-Control: public, CDN 可缓存）
        └─ 缓存未命中 → 渲染骨架 → 写缓存 → 返回
     → 浏览器加载 HTML 后，HTMX 发起片段请求
        → /fragments/* 路由（Ed25519 验签 + 租户依赖）
           → 返回片段（Cache-Control: no-store，不可缓存）
```

## 认证流程

```
登录：前端 BLAKE2b 预哈希密码 → POST /auth/login
      → 后端 Argon2id 验证 → 签发 Ed25519 JWT（内存）+ AES-GCM Refresh（Cookie）

请求：HTMX 自动注入 Authorization: Bearer <JWT>
      → Ed25519 验签 → ban_version 校验（无状态撤销）

刷新：Access Token 即将过期 → POST /auth/refresh（携带 Cookie）
      → AES-GCM 解密 Refresh → 校验 ban_version → 签发新 JWT + 轮换 Refresh

封禁：递增 User.ban_version → 所有旧 JWT 立即失效（无需 Redis 黑名单）
```

---

## 插件开发

```python
# app/plugins/myplugin/plugin.py
from fastapi import APIRouter
from app.plugins import PluginInterface, RouteProvider

class Plugin(PluginInterface, RouteProvider):
    def __init__(self):
        super().__init__("myplugin", "My Plugin", "1.0.0")

    async def initialize(self) -> bool:
        return True

    async def shutdown(self) -> bool:
        return True

    def get_routers(self) -> list[APIRouter]:
        router = APIRouter()
        @router.get("/hello")
        async def hello():
            return {"msg": "hello"}
        return [router]
```

插件目录结构：`app/plugins/myplugin/__init__.py` + `plugin.py`，启动时自动发现加载。

---

## License

AGPL-3.0
