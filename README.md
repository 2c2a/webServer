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

## 项目简介

2c2a（**Z**ero **Agent** Security Control Architecture）是一个零代理安全管控平台，专注于 Windows 主机的远程管理和权限控制。无需在目标主机安装客户端软件，基于 WinRM 协议实现远程命令执行与用户管理。

v2.0 是从 Django 同步架构**全面重写**的异步版本，贯彻**异步化**与**模块化**思想，前端绝不阻塞，原生支持插件系统与站点隔离。

### 核心特性

- **全异步非阻塞**：Granian（Rust 内核 ASGI）+ FastAPI + SQLAlchemy 2.0 Async + aiohttp
- **边缘全量缓存**：App Shell 仅依据域名解析租户配置渲染，CDN 可全量缓存；动态片段由 HTMX 独立请求
- **站点隔离**：按域名解析 SiteGroup，所有业务数据按租户过滤
- **无状态秒级令牌撤销**：ban_version 机制，无需 Redis 黑名单
- **字段级加密**：HKDF-SHA256 派生子密钥 + AES-256-GCM
- **原生插件系统**：自动发现、动态挂载路由、UI 扩展、事件钩子
- **CLI 管理工具**：`2c2a` 命令行，覆盖迁移、账户、服务器、插件、租户、密钥、静态资源

### 已移除功能（相对 v1）

- 仪表盘自定义功能（DashboardWidget / WidgetLayout）
- 隧道功能（tunnel app、Host.tunnel_* 字段、Gateway 客户端）

---

## 技术栈

| 层 | 技术 | 说明 |
| --- | --- | --- |
| ASGI 服务器 | **Granian** | Rust 内核高性能 ASGI 服务器，比 uvicorn 更快 |
| Web 框架 | **FastAPI** | 原生异步，依赖注入，自动 OpenAPI 文档 |
| ORM | **SQLAlchemy 2.0 Async** | `Mapped`/`mapped_column` 新语法，全异步会话 |
| 迁移 | **Alembic** | 异步 env.py，autogenerate |
| 模板 | **Jinja2 + JinjaX** | 组件化模板，配合 HTMX OOB |
| 前端交互 | **HTMX + HTMX OOB** | 服务端渲染片段，Out-of-Band swap，无重前端框架 |
| 任务队列 | **RedisHuey** | 替代 Celery，轻量异步任务 |
| 缓存 | **Redis (hiredis)** | 边缘缓存 + 租户缓存 + 任务 broker |
| 远程管理 | **aiohttp** | 替代同步 pywinrm，全异步 WinRM |
| 安全 | **argon2-cffi / pyjwt / cryptography** | Argon2id / Ed25519 JWT / AES-256-GCM |
| CLI | **Typer + Rich** | `2c2a` 命令行工具 |
| 配置 | **pydantic-settings** | 环境变量 + `.env` 文件 |

**Python 版本**：>= 3.12

---

## 目录结构

```
/workspace
├── app/
│   ├── main.py              # FastAPI 应用工厂 + lifespan
│   ├── core/                # 基础设施：config / db / redis / logging / exceptions
│   ├── models/              # SQLAlchemy 2.0 异步模型（按领域分文件）
│   ├── security/            # 加密原语 / JWT / 密码 / ban_version / 字段加密
│   ├── cache/               # App Shell 缓存 / HTMX 片段 / 缓存键
│   ├── tenant/              # 租户解析 / 中间件 / 依赖
│   ├── auth/                # 认证路由 / 依赖 / schemas
│   ├── api/v1/              # REST API（hosts / operations / tickets / audit）
│   ├── web/                 # 页面骨架路由 + HTMX 片段路由
│   ├── winrm/               # 异步 WinRM 客户端（transport / client / commands）
│   ├── tasks/               # RedisHuey 任务（hosts / operations）
│   ├── plugins/             # 插件系统（base / loader / manager / registry）+ example/
│   ├── templates/           # Jinja2 模板（layouts / pages / fragments）
│   ├── static/              # 应用静态资源（css / js / vendor）
│   └── cli/                 # CLI 工具（main / db / account / server / plugins / tenant / static）
├── alembic/                 # 迁移脚本
├── docs/                    # 项目文档（架构 / API / Schema / 部署）
├── pyproject.toml           # 依赖 + 2c2a 入口点 + ruff 配置
├── alembic.ini
├── .env.example
└── AGENTS.md                # 规则路由索引
```

---

## 快速开始

### 1. 环境准备

要求 Python >= 3.12。推荐使用虚拟环境：

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows
```

### 2. 安装依赖

```bash
pip install -e .
```

这会安装 `pyproject.toml` 中声明的所有依赖，并注册 `2c2a` 命令行入口点。

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：

```env
# 运行环境
ENV=development          # development / staging / production
DEBUG=true               # 开发模式
2C2A_DEMO=1              # 演示模式（自动生成密钥，WinRM 返回模拟结果）

# 数据库
DB_ENGINE=sqlite         # sqlite / postgresql / mysql
DB_NAME=2c2a

# Redis
REDIS_ENABLED=true
REDIS_URL=redis://localhost:6379/0

# 服务器
HOST=0.0.0.0
PORT=8000
WORKERS=1
```

**开发模式**（`DEBUG=true` 或 `2C2A_DEMO=1`）：未配置的密钥从 `SECRET_KEY` 自动派生，WinRM 操作返回模拟结果，无需真实 Windows 主机。

**生产模式**（`ENV=production`）：必须显式配置所有密钥，否则启动失败。

### 4. 生成密钥（生产必须）

```bash
# 一次性生成所有密钥（输出 .env 格式）
2c2a keys generate

# 或单独生成
2c2a keys secret       # SECRET_KEY
2c2a keys ed25519      # Ed25519 密钥对（JWT 签名）
2c2a keys aes          # AES-GCM 主密钥
2c2a keys blake2b      # BLAKE2b 缓存签名密钥

# 查看当前密钥配置状态
2c2a keys show
```

把生成的密钥填入 `.env`。

### 5. 初始化数据库

```bash
# 应用所有迁移
2c2a db upgrade

# 或直接 create_all（开发用，跳过迁移）
2c2a db init
```

### 6. 创建超级管理员

```bash
2c2a createsuperuser --username admin --email admin@example.com
# 交互式输入密码
```

### 7. 检查配置

```bash
2c2a serve check
```

### 8. 启动服务

```bash
# 开发模式（热重载）
2c2a serve serve --reload
# 或快捷命令
2c2a runserver --reload

# 生产模式（多 worker）
2c2a serve serve --workers 4 --host 0.0.0.0 --port 8000

# 或直接用 granian
granian --interface asgi app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 9. 启动任务消费者（可选）

WinRM 后台操作（批量用户管理、远程命令执行）通过 RedisHuey 异步执行：

```bash
2c2a serve worker
```

### 10. 收集静态资源（生产）

```bash
# 收集到 staticfiles/ 目录，供 Nginx/CDN 直接服务
2c2a collectstatic

# 或指定目录
2c2a collectstatic /var/www/static --clear
```

---

## CLI 工具

`2c2a` 命令行工具覆盖所有管理操作：

```
2c2a
├── collectstatic [dest] [--clear] [--dry-run]   # 静态资源收集
├── keys                                          # 密钥生成
│   ├── generate        # 生成所有密钥
│   ├── secret          # SECRET_KEY
│   ├── aes             # AES-GCM 主密钥
│   ├── blake2b         # BLAKE2b 签名密钥
│   ├── ed25519         # Ed25519 密钥对
│   └── show            # 查看密钥配置状态
├── db                                            # 数据库迁移
│   ├── init            # 初始化（create_all）
│   ├── migrate         # 生成迁移脚本
│   ├── upgrade         # 升级
│   ├── downgrade       # 回滚
│   ├── history         # 迁移历史
│   ├── current         # 当前版本
│   ├── heads           # 最新版本
│   └── reset           # 危险：重置数据库
├── account                                       # 账户管理
│   ├── createsuperuser # 创建超级管理员
│   ├── create          # 创建普通用户
│   ├── list            # 列出用户
│   ├── changepassword  # 修改密码
│   ├── activate        # 启用账号
│   ├── deactivate      # 禁用账号
│   ├── promote         # 提升为 staff
│   ├── demote          # 取消 staff
│   ├── superuser       # 授予/取消超级管理员
│   ├── ban             # 封禁（递增 ban_version）
│   ├── unban           # 解封
│   ├── delete          # 删除账号
│   └── info            # 查看用户详情
├── serve                                         # 服务器与运行时
│   ├── serve           # 启动 Granian ASGI 服务器
│   ├── worker          # 启动 RedisHuey 任务消费者
│   ├── shell           # 交互式 Python shell
│   └── check           # 检查配置与依赖
├── plugin                                        # 插件管理
│   ├── list            # 列出插件
│   ├── info            # 插件详情
│   ├── enable          # 启用插件
│   ├── disable         # 禁用插件
│   ├── reload          # 重新加载
│   ├── routes          # 查看路由
│   ├── services        # 查看服务
│   └── scaffold        # 生成插件骨架
├── tenant                                        # 租户管理
│   ├── list            # 列出站点组
│   ├── create          # 创建站点组
│   ├── info            # 站点组详情
│   ├── add-hostname    # 绑定域名
│   ├── remove-hostname # 解绑域名
│   ├── add-admin       # 添加管理员
│   ├── remove-admin    # 移除管理员
│   ├── activate        # 激活
│   ├── deactivate      # 停用
│   └── invalidate-cache # 清除租户缓存
├── migrate            # 快捷：migrate + upgrade
├── createsuperuser    # 快捷：创建超管
└── runserver          # 快捷：启动开发服务器
```

查看完整帮助：`2c2a --help`

---

## 核心架构

### 1. App Shell 边缘缓存 + HTMX 动态片段分离

```
请求 → TenantMiddleware（按域名解析租户，Redis 缓存）
     → App Shell 路由（仅租户配置，keyed-BLAKE2b 缓存键）
        ├─ 缓存命中 → 返回 HTML（Cache-Control: public, CDN 可缓存）
        └─ 缓存未命中 → 渲染骨架 → 写缓存 → 返回
     → 浏览器加载 HTML 后，HTMX 发起片段请求
        → /fragments/* 路由（Ed25519 验签 + 租户依赖）
           → 返回片段（Cache-Control: no-store，不可缓存）
```

**关键原则**：
- 页面骨架（HTML 壳）仅依据域名解析租户配置渲染，**绝不依赖用户状态**
- 缓存键用 keyed-BLAKE2b 签名生成，防污染、防碰撞
- 用户导航、统计等动态内容由 HTMX 在页面加载后独立请求获取

### 2. 身份认证

```
登录：前端 BLAKE2b 预哈希密码 → POST /auth/login
      → 后端 Argon2id 验证 → 签发 Ed25519 JWT（内存）+ AES-GCM Refresh（Cookie）

请求：HTMX 自动注入 Authorization: Bearer <JWT>
      → Ed25519 验签 → ban_version 校验（无状态撤销）

刷新：Access Token 即将过期 → POST /auth/refresh（携带 Cookie）
      → AES-GCM 解密 Refresh → 校验 ban_version → 签发新 JWT + 轮换 Refresh

封禁：递增 User.ban_version → 所有旧 JWT 立即失效（无需 Redis 黑名单）
```

| Token | 算法 | 有效期 | 存储 | 用途 |
| --- | --- | --- | --- | --- |
| Access Token | Ed25519 签名 JWT | 5 分钟 | 前端内存（防 XSS） | API 认证 |
| Refresh Token | AES-GCM 加密 | 7 天 | HttpOnly Cookie（防 XSS 读取） | 刷新 Access Token |

**密码哈希链路**：
- 前端 BLAKE2b 预哈希（digest_size=64，防超长密码 DoS 后端 Argon2id）
- 后端 Argon2id 加盐慢哈希（抗 GPU/ASIC 爆破，内存硬）

### 3. 字段级加密

- HKDF-SHA256 按字段名派生子密钥
- AES-256-GCM 加密
- 每个敏感字段独立密钥，防跨字段关联、防篡改
- 适用：手机号、邮箱、身份证、地址等 PII

### 4. 站点隔离

```
请求域名 → resolve_tenant_by_hostname()
          ├─ Redis 缓存命中 → 返回 SiteGroup
          └─ 查 SiteGroupHostname 表 → 返回 SiteGroup
             └─ 未匹配 → 回退默认租户

所有业务查询：WHERE site_group_id = tenant.site_group_id
```

### 5. 插件系统

```python
# app/plugins/myplugin/plugin.py
from fastapi import APIRouter
from app.plugins.base import PluginInterface, RouteProvider

class MyPlugin(PluginInterface, RouteProvider):
    def __init__(self):
        super().__init__(
            plugin_id="myplugin",
            name="My Plugin",
            version="1.0.0",
            description="示例插件",
        )

    async def initialize(self) -> None:
        """启动时初始化。"""
        pass

    async def shutdown(self) -> None:
        """关闭时清理。"""
        pass

    def get_routes(self) -> tuple[str, APIRouter]:
        """提供路由：返回 (prefix, router)。"""
        router = APIRouter()

        @router.get("/hello")
        async def hello():
            return {"msg": "hello"}

        return ("/myplugin", router)
```

插件能力：
- **RouteProvider**：提供 FastAPI 路由，启动时自动挂载
- **ServiceProvider**：注册可复用服务
- **UIExtensionProvider**：注册 JinjaX 组件扩展点
- **EventHook**：事件钩子，async emit 并发执行

插件管理：
```bash
2c2a plugin list                # 列出所有插件
2c2a plugin info <plugin_id>    # 查看详情
2c2a plugin enable <plugin_id>  # 启用
2c2a plugin disable <plugin_id> # 禁用
2c2a plugin reload              # 重新加载
2c2a plugin routes              # 查看所有插件路由
2c2a plugin scaffold <id>       # 生成插件骨架
```

---

## 配置参考

完整配置见 `.env.example`，关键项：

### 运行环境

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ENV` | `production` | `development` / `staging` / `production` |
| `DEBUG` | `false` | 开发模式，开启后密钥可从 SECRET_KEY 派生 |
| `2C2A_DEMO` | `0` | 演示模式，WinRM 返回模拟结果 |

### 数据库

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DB_ENGINE` | `sqlite` | `sqlite` / `postgresql` / `mysql` |
| `DB_NAME` | `2c2a` | 数据库名 |
| `DB_HOST` | `localhost` | 主机（PG/MySQL） |
| `DB_PORT` | `5432` | 端口（PG/MySQL） |
| `DB_USER` | `2c2a` | 用户名 |
| `DB_PASSWORD` | - | 密码 |
| `DB_POOL_SIZE` | `10` | 连接池大小 |

### Redis

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `REDIS_ENABLED` | `true` | 是否启用 Redis |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接 URL |

### 密钥（生产必须）

| 变量 | 说明 | 生成命令 |
| --- | --- | --- |
| `SECRET_KEY` | 通用密钥 | `2c2a keys secret` |
| `ED25519_PRIVATE_KEY_PEM` | JWT 签名私钥 | `2c2a keys ed25519` |
| `ED25519_PUBLIC_KEY_PEM` | JWT 验签公钥 | 同上 |
| `CRYPTO_MASTER_KEY_B64` | AES-GCM 主密钥（32 字节 base64） | `2c2a keys aes` |
| `CACHE_SIGNING_KEY` | BLAKE2b 缓存签名密钥 | `2c2a keys blake2b` |

### 认证

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ACCESS_TOKEN_TTL_SECONDS` | `300` | Access Token 有效期（5 分钟） |
| `REFRESH_TOKEN_TTL_DAYS` | `7` | Refresh Token 有效期（7 天） |

### Argon2id

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `ARGON2_TIME_COST` | `3` | 时间成本 |
| `ARGON2_MEMORY_COST` | `65536` | 内存成本（64 MiB） |
| `ARGON2_PARALLELISM` | `2` | 并行度 |

---

## 部署

### 生产部署清单

1. **环境变量**：`ENV=production`，`DEBUG=false`，配置所有密钥
2. **数据库**：用 PostgreSQL 或 MySQL，不要用 SQLite
3. **Redis**：启用，用于缓存和任务队列
4. **静态资源**：`2c2a collectstatic /var/www/static --clear`，Nginx 直接服务
5. **进程管理**：用 systemd / supervisor 管理 Granian 和 Huey worker
6. **反向代理**：Nginx 转发到 Granian，处理 TLS、静态文件、缓存

### Nginx 配置示例

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 静态资源直接服务
    location /static/ {
        alias /var/www/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # App Shell 边缘缓存
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # App Shell 可缓存
        proxy_cache_valid 200 5m;
    }

    # HTMX 片段不缓存
    location /fragments/ {
        proxy_pass http://127.0.0.1:8000;
        add_header Cache-Control "no-store";
    }
}
```

### systemd 服务示例

```ini
# /etc/systemd/system/2c2a-web.service
[Unit]
Description=2c2a Web Server (Granian)
After=network.target redis.service postgresql.service

[Service]
Type=simple
User=2c2a
WorkingDirectory=/opt/2c2a
EnvironmentFile=/opt/2c2a/.env
ExecStart=/opt/2c2a/.venv/bin/2c2a serve serve --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/2c2a-worker.service
[Unit]
Description=2c2a Task Worker (Huey)
After=network.target redis.service

[Service]
Type=simple
User=2c2a
WorkingDirectory=/opt/2c2a
EnvironmentFile=/opt/2c2a/.env
ExecStart=/opt/2c2a/.venv/bin/2c2a serve worker
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 开发

### 开发流程

```bash
# 1. 启动开发服务器（热重载）
2c2a runserver --reload

# 2. 启动任务消费者（另一个终端，如需测试 WinRM 任务）
2c2a serve worker

# 3. 修改模型后生成迁移
2c2a db migrate -m "描述变更"
2c2a db upgrade

# 4. 代码风格检查
ruff check app/

# 5. 格式化
ruff format app/
```

### 交互式 Shell

```bash
2c2a serve shell
# 预加载应用上下文，可直接操作模型
```

### 项目规范

- **AGENTS.md**：规则路由索引，按任务类型加载对应规则
- **.trae/rules/**：细分规则文件（异步模式、安全、缓存、租户、数据库、迁移、插件、前端、CLI、WinRM、API、Git、故障排查）
- **docs/**：架构设计、API 文档、数据库 Schema、部署运维、安全配置

修改架构或核心机制前先读对应文档和规则。

---

## License

AGPL-3.0
