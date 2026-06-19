# AGENTS.md

2c2a（Zero Agent Security Control Architecture）异步架构项目。
详细规范按任务类型从 `.trae/rules/` 加载对应规则文件。

## 如何使用规则

接到任务后，**先按下表加载对应的规则文件**，再动手。规则文件位于 `.trae/rules/`。

| 任务类型 / 关键词 | 规则文件 |
| --- | --- |
| 任何任务开始前必读 | `01-iron-laws.md` |
| 了解项目整体 / 目录结构 / 技术栈 | `00-overview.md` |
| 写 async/await / 数据库查询 / HTTP 调用 | `02-async-patterns.md` |
| 密码 / JWT / 加密 / 密钥 / ban_version | `03-security.md` |
| 缓存 / App Shell / HTMX 片段 / ETag | `04-caching.md` |
| 租户 / 站点组 / 域名解析 / 多租户 | `05-tenant.md` |
| 新增/修改模型 / ORM 查询 / Mixin | `06-database.md` |
| Alembic / 迁移 / upgrade / downgrade | `07-migrations.md` |
| 插件 / PluginInterface / RouteProvider | `08-plugins.md` |
| 模板 / JinjaX / HTMX / 静态资源 / collectstatic | `09-frontend.md` |
| CLI / 2c2a 命令 / Typer / 账户管理 | `10-cli.md` |
| WinRM / 远程命令 / Windows 主机管理 | `11-winrm.md` |
| API 路由 / 依赖注入 / FastAPI 端点 | `12-api.md` |
| Git / 分支 / 提交 / PR | `13-git.md` |
| 调试 / 环境问题 / 端口冲突 / 依赖报错 | `14-troubleshooting.md` |

**不确定加载哪个？** 先读 `00-overview.md` 和 `01-iron-laws.md`，再按上表匹配。
匹配多个时全部加载。宁可多读，不可漏读。

## 快速参考

- **运行命令**：所有 Python 命令用 `uv run`（见 `01-iron-laws.md`）
- **CLI 入口**：`uv run 2c2a --help` 或 `uv run python -m app.cli`
- **启动服务器**：`uv run 2c2a serve serve` 或 `uv run granian --interface asgi app.main:app`
- **生成密钥**：`uv run 2c2a keys generate`
- **数据库迁移**：`uv run 2c2a db upgrade`
- **项目文档**：`docs/` 目录下有架构、API、数据库 Schema、部署运维等文档
