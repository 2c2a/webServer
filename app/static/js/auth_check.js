// 2c2a 主页登录态探测
// 用于公开页（如 homepage）被动探测登录态，已登录用户把「登录」按钮改为「进入控制台」。
// 与 auth_guard.js 区分：auth_guard 是 HTMX 401 拦截，本文件是页面加载后一次性探测。
//
// 依赖：页面中需有 #nav-login-btn 和 #hero-login-btn（可选）元素。
// 不依赖 window.__ACCESS_TOKEN__：homepage 不注入 access_token，
// 探测完全依赖 HttpOnly Refresh Cookie（get_current_user_optional 会回退到 cookie）。
(function() {
    function applyLoggedIn(username) {
        // 顶栏「登录」→「进入控制台」
        var navBtn = document.getElementById('nav-login-btn');
        if (navBtn) {
            navBtn.href = '/dashboard';
            navBtn.textContent = '进入控制台';
        }
        // Hero「立即登录」→「进入控制台」，图标换成箭头进入
        var heroBtn = document.getElementById('hero-login-btn');
        var heroText = document.getElementById('hero-login-text');
        var heroIcon = document.getElementById('hero-login-icon');
        if (heroBtn) heroBtn.href = '/dashboard';
        if (heroText) heroText.textContent = '进入控制台';
        if (heroIcon) {
            // 替换为「右箭头进入方块」图标，表示进入控制台
            heroIcon.innerHTML = '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M8 12h8"/><path d="M12 8v8"/>';
        }
    }

    fetch('/auth/me', { credentials: 'include' }).then(function(r) {
        if (r.ok) return r.json().then(function(data) { return data; });
        return null;
    }).then(function(data) {
        if (data) applyLoggedIn(data.username);
    }).catch(function() {});
})();
