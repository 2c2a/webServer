# 09 - 前端与模板

## 技术栈

- **Jinja2**：页面模板
- **JinjaX**：组件化模板
- **HTMX + HTMX OOB**：服务端渲染片段
- **CSS**：`app/static/css/base.css`

## 模板目录

```
app/templates/
├── layouts/app_shell.html      # App Shell 基础布局
├── pages/                      # 页面模板
└── fragments/                  # HTMX 动态片段
```

## App Shell 布局原则

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
├── css/base.css        # 全局样式
├── js/auth.js          # 认证 JS
└── vendor/htmx.min.js  # 第三方库（本地化，禁 CDN）
```

### collectstatic

```bash
2c2a collectstatic                     # 收集到 staticfiles/
2c2a collectstatic /var/www/static --clear
2c2a collectstatic --dry-run           # 仅预览
```

收集后包含应用静态 + 插件静态（`staticfiles/plugins/<id>/`）。

## 样式规范

1. 禁止内联样式
2. 禁止 CDN 链接
3. 样式统一放 base.css，按模块注释分隔