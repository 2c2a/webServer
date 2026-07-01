// 2c2a HTMX 401 全局拦截
// 与 auth.js 解耦：不依赖 window.__ACCESS_TOKEN__，所有布局（含未登录页）都加载。
//
// 工作方式：
// - 监听 htmx:beforeOnLoad，遇到 401 时阻止 toast 渲染并跳转到 /login?next=<当前路径>
// - 与后端 HX-Redirect 兜底配合：后端会在 401 响应头加 HX-Redirect，
//   但有些 HTMX 场景（如 hx-swap=oob、htmx:abort）可能跳过该头处理，
//   本监听器作为前端兜底，保证一致性。
// - 已在 /login 页时不重复跳转，避免循环。
(function() {
    function loginRedirectUrl() {
        var path = location.pathname;
        var search = location.search;
        var next = path + search;
        return '/login?next=' + encodeURIComponent(next);
    }

    function isOnLoginPage() {
        return location.pathname === '/login' || location.pathname === '/register'
            || location.pathname === '/forgot-password' || location.pathname === '/reset-password';
    }

    document.addEventListener('htmx:beforeOnLoad', function(evt) {
        var xhr = evt.detail && evt.detail.xhr;
        if (!xhr) return;
        if (xhr.status === 401) {
            // 阻止默认的 toast 渲染
            evt.detail.shouldSwap = false;
            if (!isOnLoginPage()) {
                location.href = loginRedirectUrl();
            }
        }
    });
})();
