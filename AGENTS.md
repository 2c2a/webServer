# 2c2a 项目 - AI Agent 绝对开发规范

## 0. 核心铁律（违反即严重错误）

- **环境**：所有 Python 命令必须通过 `uv run` 执行。
- **后台**：提供商/用户后台严禁使用 Django-Admin，必须手搓。
- **样式**：严禁编写原生 `<style>` 或内联样式，必须使用 Tailwind 原子类。
- **组件**：严禁使用 Bootstrap (`django-bootstrap5`)。
- **双轨隔离**：前台（用户端）与后台（提供商端）样式严禁混用，必须严格遵循对应区域的公式。
- **本地化**：严禁引用任何 CDN 资源（包括但不限于 fonts.googleapis.com、cdn.jsdelivr.net、unpkg.com 等），所有字体、JS 库、CSS 框架、图标字体等线上资源必须拉取到本地 `static/vendor/` 目录后引用。

***

## 1. Python 环境与命令规范

### 1.1 命令执行标准

```bash
# ❌ 绝对禁止
.venv/bin/python manage.py runserver
python manage.py runserver
pip install package
# ✅ 唯一正确方式
uv run python manage.py runserver
uv add package
```

### 1.2 依赖管理

```bash
uv sync               # 同步环境
uv add package-name   # 添加生产依赖
uv add --dev package  # 添加开发依赖
uv remove package     # 移除依赖
```

### 1.3 开发服务器启停规则

- **启动前**：必须执行 `lsof -i :8000` 检查端口。
- **仅改前端 (HTML/CSS/JS)**：**严禁杀进程**，直接刷新浏览器。
- **改了 Python 代码**：必须杀进程后重启 `kill -9 $(lsof -t -i:8000)`。
- **严禁**同时启动多个占用不同端口的 Python 进程。

### 1.4 常用脚本

```bash
uv run python manage.py makemigrations && uv run python manage.py migrate
uv run celery -A config worker -l info
uv run pytest
```

***

## 2. 前端 UI 架构规范

### 2.1 技术栈锁定（不可替换）

- **样式**：Tailwind CSS (必须使用独立 CLI 构建，**严禁 CDN**)
- **字体**：严禁通过 CDN 加载 Google Fonts 或任何在线字体服务，必须下载字体文件到本地 `static/` 后用 `@font-face` 声明。
- **图标**：Material Symbols 字体文件必须本地化，严禁 CDN 链接。
- **JS 库**：Alpine.js 等交互库必须下载到本地 `static/`，严禁 `<script src="https://...">`。
- **组件化**：`django-cotton` (所有复用 UI 必须封装为 `<x-xxx>` 标签，按区域区分如 `<x-front.card>` / `<x-admin.card>`)
- **交互**：Alpine.js (仅处理弹窗/菜单，**严禁 Vue/React**)
- **接口**：`djangorestframework` (所有无刷新操作必须走 API)

### 2.2 前台样式公式（面向普通用户）

**设计语言**：Material Design 3 (MD3) + 毛玻璃
**严禁自由发挥，全局必须严格套用以下公式（使用** **`md:`** **命名空间）：**

- **毛玻璃卡片**：`bg-md-surface-container/70 backdrop-blur-xl border border-white/10 rounded-md-lg shadow-2xl`
- **MD3 输入框**：`w-full bg-md-surface/50 border border-md-outline/50 rounded-md px-4 py-3 text-md-on-surface placeholder-md-outline focus:outline-none focus:ring-2 focus:ring-md-primary transition`
- **圆角规范**：按钮/输入框 `rounded-md` (12px) | 卡片 `rounded-md-lg` (16px) | 弹窗/FAB `rounded-md-xl` (28px)。**严禁出现直角或小圆角。**

### 2.3 后台样式公式（面向提供商/主机管理）

**设计语言**：科技监控风 + 毛玻璃
**严禁自由发挥，全局必须严格套用以下公式（直接使用 Tailwind 原生** **`slate/cyan`** **色系，严禁使用** **`md:`** **命名空间）：**

- **暗色模式基准**：全站强制深色，背景必须使用极深色 `slate-950` 或 `slate-900`。
- **科技风毛玻璃卡片**：`bg-slate-950/70 backdrop-blur-xl border border-slate-700/50 rounded-md shadow-none`
- **发光输入框**：`w-full bg-slate-900/50 backdrop-blur-sm border border-slate-700/50 rounded px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500/50 focus:border-cyan-500 transition`
- **科技风主按钮**：`bg-cyan-600 hover:bg-cyan-500 text-white px-4 py-2 rounded-md font-medium shadow-[0_0_15px_-3px_rgba(34,211,238,0.3)] transition`
- **科技风毛玻璃弹窗**：`bg-slate-950/80 backdrop-blur-2xl border border-cyan-500/20 rounded-lg shadow-2xl`
- **圆角规范**：统一使用标准圆角 `rounded-md` (6px) 或 `rounded-lg` (8px)。**严禁出现 MD3 的大圆角 (16px/28px)。**

### 2.4 图标规范（前后台通用）

- 统一使用 `<span class="material-symbols-rounded">icon_name</span>`。
- 后台图标颜色强制使用 `text-cyan-400` 或 `text-slate-400`，严禁使用 MD3 的紫色。

***

## 3. 核心业务开发模式

### 3.1 复杂表单（如：上架主机）

```python
# ❌ 禁止：在一个页面垂直堆叠长表单
class HostCreateView(TemplateView): ...
# ✅ 必须：使用 django-formtools 实现分步向导
from formtools.wizard.views import SessionWizardView
class HostDeployWizard(SessionWizardView): ...
```

**模板渲染**：严禁 `{{ form.as_p }}`，必须 `{% for field in form %}` 循环。后台表单必须套用 \[2.3 的发光输入框公式]。

### 3.2 快捷操作（如：一键生成邀请链接）

**前端套路**：Alpine.js 监听点击 -> `fetch` 调用 DRF POST 接口 -> `<template x-if>` 弹窗显示结果。

- 前台弹窗：套用 \[2.2 的 MD3 毛玻璃弹窗公式]
- 后台弹窗：套用 \[2.3 的科技风毛玻璃弹窗公式]

### 3.3 页面布局

- **严禁**在业务视图里堆砌深层 `<div>`。
- **必须**按区域封装 `django-cotton` 组件（如前台 `<x-front.nav>`，后台 `<x-admin.sidebar>`）。

***

## 4. 故障排查速查

```bash
# 依赖炸了
rm -rf .venv && uv sync
# 迁移冲突
uv run python manage.py showmigrations
uv run python manage.py migrate --run-syncdb
# 测试账号 (仅限本地)
# 超管：admin / admin
# 提供商：provider / provider
# 普通用户：user / user
```

## 5. 分支规范（分阶段发布模型）

所有 2c2a 生态仓库统一采用 **5 级分阶段分支模型**：

| 分支 | 阶段 | 用途 | 部署环境 |
|------|------|------|----------|
| `master` | 生产版本 | 线上稳定运行，仅接受 hotfix 合并 | 生产服务器 |
| `beta` | 公测版本 | 服务器端集成测试，QA 验证通过后方可合入 master | 预发布/测试服务器 |
| `alpha` | 内测版本 | 本地开发机测试，功能验证与联调 | 本地开发环境 |
| `hotfix/*` | 热修补 | 紧急修复线上问题，从 master 切出，修复后合并回 master 并同步 beta/alpha | 临时生产修复 |
| `feat/*` | 功能开发 | 新功能迭代分支，开发完成后合并至 alpha 进入内测 | 本地开发环境 |


**合并流向**：`feat` → `alpha` → `beta` → `master`，`hotfix` 可直接回灌各分支。

### 5.1 开发工作流（含清理）
```bash
# 1. 从 alpha 切出功能分支
git checkout -b feat/user-auth origin/alpha
# 2. 开发完成后合并至 alpha 进行本地测试
git checkout alpha
git merge feat/user-auth
# 3. 本地测试通过后提 PR 合并至 beta 进行服务器公测
gh pr create --base beta --head alpha --title "feat: user auth"
# 4. 【强制清理】PR 合并后，必须立即删除本地和远程功能分支
git push origin --delete feat/user-auth  # 删除远程分支 (若已推送)
git branch -d feat/user-auth            # 删除本地分支
```
### 5.2 热修补紧急流程（含清理）
```bash
# 1. 从 master 切出 hotfix
git checkout -b hotfix/critical-bug origin/master
# 2. 修复后合并回 master
git checkout master
git merge hotfix/critical-bug
# 3. 同步回灌 beta / alpha
git checkout beta && git merge master
git checkout alpha && git merge master
# 4. 【强制清理】回灌完毕后，必须立即删除本地和远程热修分支
git push origin --delete hotfix/critical-bug  # 删除远程分支 (若已推送)
git branch -d hotfix/critical-bug             # 删除本地分支
```

### 5.3 Git 分支生命周期铁律（违反即严重错误）
- **临时性原则**：`feat/*` 和 `hotfix/*` 是一次性分支，严禁长期存留。
- **强制清理**：✅ 任何 `feat/*` 或 `hotfix/*` 分支在成功合并至主干（`alpha`/`beta`/`master`）后，**必须立即删除本地和远程分支**。
- **禁止骑驴找马**：❌ 严禁在已合并的 `feat/*` 分支上继续开发新功能，必须从最新的主干切出新分支。

***

**系统提示：作为 AI Agent，在生成模板代码时，必须首先判断当前路由属于“前台”还是“后台”，严禁跨区域套用样式公式。凡是触发“❌ 绝对禁止”项的，必须自我纠正。**
