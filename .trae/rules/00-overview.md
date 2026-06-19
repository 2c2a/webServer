# 00 - 项目概览

## 项目定位

2c2a = **Zero Agent Security Control Architecture**。从 Django 同步架构全量重写为异步架构，核心目标：高性能、不阻塞前端、原生插件系统、原生站点隔离。

## 技术栈

| 层 | 技术 | 说明 |
| --- | --- | --- |
| ASGI 服务器 | Granian | 比 uvicorn 更高性能的 Rust 实现 |
| Web 框架 | FastAPI | 异步路由、依赖注入 |
| ORM | SQLAlchemy 2.0 Async | `Mapped`/`mapped_column` 新语法，全异步 |
| 迁移 | Alembic | 异步 env.py |
| 模板 | Jinja2 + JinjaX | 组件化模板 |
| 前端交互 | HTMX + HTMX OOB | 服务端渲染片段，无重前端框架 |
| 任务队列 | RedisHuey | 替代 Celery，更轻量 |
| Redis | redis[hiredis] | 缓存 + 队列 + 租户解析缓存 |
| 远程执行 | aiohttp | 替代同步 winrm，全异步 WS-Management |
| 安全 | argon2-cffi / pyjwt / cryptography | Argon2id / Ed25519 JWT / AES-256-GCM |
| CLI | Typer + Rich | `2c2a` 命令行工具 |
| 配置 | pydantic-settings | 环境变量 + `.env` |

Python 版本：**>=3.12**

## 目录结构

```
app/
├── main.py              # FastAPI 应用工厂 + lifespan
├── core/                # 基础设施：config / db / redis / logging / exceptions
├── models/              # SQLAlchemy 模型（按领域分文件）
├── security/            # 加密原语 / JWT / 密码 / ban_version / 字段加密
├── cache/               # App Shell 缓存 / HTMX 片段 / 缓存键
├── tenant/              # 租户解析 / 中间件 / 依赖
├── auth/                # 认证路由 / 依赖 / schemas
├── api/v1/              # REST API（hosts / operations / tickets / audit）
├── web/                 # 页面骨架路由 + HTMX 片段路由
├── winrm/               # 异步 WinRM 客户端（transport / client / commands）
├── tasks/               # RedisHuey 任务（hosts / operations）
├── plugins/             # 插件系统（base / loader / manager / registry）+ example/
├── templates/           # Jinja2 模板（layouts / pages / fragments）
├── static/              # 应用静态资源（css / js / vendor）
└── cli/                 # CLI 工具（main / db / account / server / plugins / tenant / static）
```

## 核心架构理念

1. **App Shell 边缘全量缓存 + HTMX 动态片段分离**
   - 页面骨架（HTML 壳）仅依据域名解析租户配置渲染，绝不依赖用户状态 → 可被 CDN 全量缓存
   - 用户导航、统计等动态内容由 HTMX 在页面加载后独立请求获取 → 不可缓存

2. **站点隔离**
   - 按域名解析 `SiteGroup`，所有业务数据按 `site_group_id` 过滤
   - 中间件层注入 `TenantContext`，依赖注入层强制过滤

3. **无状态秒级令牌撤销**
   - JWT Payload 携带 `ban_version`，封禁时递增数据库版本号
   - 无需 Redis 黑名单，验签时比对版本号即可

4. **字段级加密**
   - HKDF-SHA256 按字段名派生子密钥 + AES-256-GCM 加密
   - 每个敏感字段独立密钥，防篡改、防跨字段关联