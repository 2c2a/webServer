# 09 - 前端与模板

## 技术栈

- **Jinja2**：页面模板
- **JinjaX**：组件化模板
- **HTMX + HTMX OOB**：服务端渲染片段
- **CSS**：`app/static/css/base.css`（遗留 base.css 页面）

## 两套前端体系

项目存在两套前端，均源自 `.design` 设计文件，**设计优先**：

| 体系 | 设计库 | 设备 | 布局 | 主题前缀 |
| --- | --- | --- | --- | --- |
| 管理后台 `2c2a-admin-console` | Vercel | desktop | 左侧边栏 + 顶栏 | `--vercel-*` |
| 用户前台 `2c2a-frontend` | TRAE Work | mobile | 顶部导航 + 底部 Tab | `--c-*` |

两套体系均使用 **Tailwind CSS（浏览器构建，本地化）+ Lucide 图标（本地化）+ CSS 变量内联主题**。所有资源**必须**下载到 `app/static/vendor/` 本地服务，禁止 CDN（铁律 8）。

## 模板目录

```
app/templates/
├── layouts/
│   ├── app_shell.html         # 遗留 App Shell 基础布局（base.css）
│   ├── admin_shell.html       # 管理后台布局（Vercel 主题 + 侧边栏 + 顶栏）
│   └── frontend_shell.html    # 用户前台布局（TRAE Work 主题 + 顶/底导航）
├── pages/
│   ├── admin/                 # 管理后台页面（继承 admin_shell）
│   ├── *.html                 # 用户前台页面（继承 frontend_shell 或独立）
│   └── (遗留 base.css 页面)
└── fragments/                 # HTMX 动态片段
```

## App Shell 布局原则（遗留 base.css 体系）

1. **仅含租户级配置**：站点名、主题、ICP
2. **绝不含用户状态**：无用户名、无个性化数据
3. **动态内容用 HTMX 加载**

```html
<nav id="main-nav"
     hx-get="/fragments/nav"
     hx-trigger="load"
     hx-target="this"
     hx-swap="innerHTML">
    <span class="placeholder">...</span>
</nav>
```

## .design 体系布局约定

- **admin_shell.html**：侧边栏导航 + 顶栏面包屑，通过 `active_nav` 变量高亮当前项；页面提供 `{% block content %}`。
- **frontend_shell.html**：顶部品牌栏 + 底部 Tab 栏，通过 `active_nav` 变量高亮当前 Tab；页面提供 `{% block content %}`。登录/注册页无导航，独立模板。
- 设计页内的演示数据（人名、数字等）为占位内容，真实数据应通过 HTMX 片段或 API 注入；在接入后端前可保留占位以保持视觉完整。

## HTMX 模式

### 页面加载后请求片段

```html
<div id="stats"
     hx-get="/fragments/stats"
     hx-trigger="load"
     hx-target="this"
     hx-swap="innerHTML">
    <span class="loading">加载中...</span>
</div>
```

### OOB（Out of Band）

```html
<div id="main-content">主内容...</div>
<div id="main-nav" hx-swap-oob="true">新导航...</div>
<div id="stats" hx-swap-oob="true">新统计...</div>
```

## 静态资源

```
app/static/
├── css/base.css                 # 遗留全局样式（base.css 体系）
├── js/auth.js                   # 认证 JS
└── vendor/
    ├── htmx.min.js              # HTMX（本地化）
    ├── tailwind-browser.min.js  # Tailwind CSS 浏览器构建（.design 体系）
    └── lucide.min.js            # Lucide 图标 UMD（.design 体系）
```

### collectstatic

```bash
2c2a collectstatic                     # 收集到 staticfiles/
2c2a collectstatic /var/www/static --clear
2c2a collectstatic --dry-run           # 仅预览
```

收集后包含应用静态 + 插件静态（`staticfiles/plugins/<id>/`）。

## 样式规范

> 当 `.design` 样式与本规范冲突时，**以 `.design` 为准**（用户明确要求）。

1. **遗留 base.css 体系**：禁止内联样式、禁止 CDN，样式统一放 `base.css`，按模块注释分隔。
2. **`.design` 体系（admin_shell / frontend_shell 及其页面）**：
   - 使用本地化的 Tailwind 浏览器构建（`/static/vendor/tailwind-browser.min.js`）与 Lucide UMD（`/static/vendor/lucide.min.js`），**禁止 CDN**（铁律 8）。
   - 允许使用内联 `style` 与 CSS 变量（`--vercel-*` / `--c-*`）承载主题 token。
   - 主题 token 应集中在布局模板的 `<style id="theme-vars">` 中，页面模板只写内容与 Tailwind 类，避免重复内联大段 CSS。
   - 不得在 `.design` 体系页面引入 `base.css`，以免选择器冲突。
