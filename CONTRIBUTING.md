# 贡献指南 (Contributing Guide)

感谢您有兴趣为 2c2a 项目做出贡献！本文档旨在为您提供有关如何参与项目开发的详细指导。

## 目录

- [行为准则](#行为准则)
- [开发环境设置](#开发环境设置)
- [代码规范](#代码规范)
- [提交指南](#提交指南)
- [报告问题](#报告问题)
- [拉取请求](#拉取请求)
- [技术架构](#技术架构)

## 行为准则

请遵守我们的行为准则，营造积极友好的社区环境。尊重他人观点，建设性地讨论技术问题。

## 开发环境设置

### 环境要求

- Python 3.10+
- PostgreSQL 12+ 或 MySQL 8.0+ 或 SQLite
- Redis 6.0+ (可选，用于异步任务)

### 设置步骤

1. Fork 仓库
```bash
git clone https://github.com/YOUR_USERNAME/2c2a.git
cd 2c2a
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 文件，配置数据库等连接信息
```

5. 数据库迁移
```bash
python manage.py makemigrations
python manage.py migrate
```

6. 创建超级用户
```bash
python manage.py createsuperuser
```

7. 安装 Tailwind CSS CLI（前端样式开发需要）

Tailwind CSS 的 standalone CLI 可执行文件未纳入 git 仓库（超过 GitHub 文件大小限制），首次 clone 后需手动下载：

```bash
# Linux x64
curl -fSL -o static/vendor/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-linux-x64
chmod +x static/vendor/tailwindcss

# Linux ARM64
curl -fSL -o static/vendor/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-linux-arm64
chmod +x static/vendor/tailwindcss

# macOS ARM64 (Apple Silicon)
curl -fSL -o static/vendor/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-macos-arm64
chmod +x static/vendor/tailwindcss

# macOS x64 (Intel)
curl -fSL -o static/vendor/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.4/tailwindcss-macos-x64
chmod +x static/vendor/tailwindcss
```

或者直接运行构建脚本，它会自动检测平台并提示下载：

```bash
./scripts/tailwind-build.sh
```

构建 Tailwind CSS 样式文件：

```bash
./scripts/tailwind-build.sh          # 一次性构建
./scripts/tailwind-build.sh --watch  # 监听模式（开发时推荐）
```

> **注意**：如果只是运行项目而不修改 Tailwind 样式，无需下载 CLI。`static/css/provider.css` 已包含构建后的样式，Django 可直接使用。

## 代码规范

### Python 代码规范

- 遵循 PEP 8 代码风格指南
- 使用 4 个空格缩进
- 变量和函数名使用 snake_case 命名法
- 类名使用 CamelCase 命名法
- 单行长度不超过 88 个字符
- 所有代码必须有适当的注释和文档字符串

### Django 特定规范

- 遵循 Django 的最佳实践
- Model、View、Form 等组件遵循单一职责原则
- 使用 Django ORM 而非原生 SQL
- 正确使用 Django 信号和中间件

### 前端代码规范

- HTML 使用语义化标签
- CSS 遵循 BEM 命名方法论
- JavaScript 使用 ES6+ 语法
- 遵循响应式设计原则

### 项目特定规范

- 使用自定义用户模型：所有与用户的外键关联都必须通过 `settings.AUTH_USER_MODEL` 引用，而不是直接指向 `auth.User`
- 验证码系统集成：按照项目现有的 Geetest v4 或 Turnstile 集成方式进行扩展
- WinRM 客户端封装：复用 `utils.winrm_client.WinrmClient` 类，避免重复造轮子

## 提交指南

### 分支管理

- `main` 分支：稳定版本，保护分支
- `develop` 分支：开发版本
- 功能分支：`feature/功能名称`
- 修复分支：`fix/问题描述`
- 发布分支：`release/版本号`

### 提交信息

使用清晰、简洁的提交信息，遵循格式：

```
type(scope): 描述信息

可选的正文内容
- 更详细的描述
- 可以包含多个要点
```

类型包括：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构代码
- `test`: 测试相关
- `chore`: 构建过程或辅助工具变动

## 报告问题

当报告问题时，请包含以下信息：

- 详细的错误描述
- 重现步骤
- 预期行为
- 实际行为
- 环境信息（操作系统、Python 版本等）
- 相关的日志信息

## 拉取请求

### 创建 PR

1. 确保您的分支基于最新的 `develop` 分支
2. 提交清晰的提交信息
3. 在 PR 描述中说明变更内容
4. 如果修复了某个 Issue，请在描述中提及

### PR 要求

- 保持 PR 专注，每次只解决一个问题
- 确保 CI 检查通过
- 添加必要的测试
- 更新相关文档
- 遵循代码规范

## 技术架构

### 项目结构

```
2c2a/
├── apps/
│   ├── accounts/       # 用户管理应用
│   ├── hosts/          # 主机管理应用
│   ├── operations/     # 操作记录应用（含开户系统）
│   └── dashboard/      # 仪表盘应用
├── config/             # 配置文件
├── static/             # 静态文件
├── templates/          # 模板文件
├── utils/              # 工具函数
├── manage.py
├── requirements.txt
├── README.md
└── CONTRIBUTING.md     # 本文件
```

### 核心组件

- **用户管理**: 自定义用户模型，支持注册、登录、验证等功能
- **主机管理**: 管理云电脑主机信息，支持 WinRM 连接
- **开户系统**: 用户开户申请、审核和处理流程
- **验证系统**: Geetest v4 和 Turnstile 验证码集成
- **WinRM 客户端**: 用于远程主机管理的封装类

### 安全考虑

- 所有用户输入必须经过验证
- 使用 Django 表单进行数据验证
- 防止 SQL 注入、XSS 攻击和 CSRF 攻击
- 实施适当的权限验证
- 使用 Django 内置权限系统
- 敏感操作需二次确认

## 测试

### 运行测试

```bash
# 运行所有测试
python manage.py test

# 运行特定应用的测试
python manage.py test apps.accounts

# 运行特定测试
python manage.py test apps.accounts.tests.test_geetest
```

### 测试覆盖

- 新功能必须包含单元测试
- 修改现有功能需确保测试通过
- 重要逻辑需编写集成测试

## 文档

- 函数和类必须有文档字符串
- 复杂逻辑需添加注释
- API 变更需更新相关文档

## 社区

- 问题和讨论在 GitHub Issues 中进行
- 代码审查通过 Pull Request 进行
- 及时响应评论和反馈

## 许可证

本项目使用 GPL 2.0 许可证。提交代码即表示您同意按此许可证发布您的贡献。