// 2c2a 前端认证逻辑
// Access Token 存放于内存（防 XSS），过期前自动刷新

(function() {
    const REFRESH_THRESHOLD = 60; // 过期前 60 秒刷新

    function scheduleRefresh() {
        const expiresIn = window.__TOKEN_EXPIRES_IN__ || 300;
        const refreshIn = Math.max((expiresIn - REFRESH_THRESHOLD) * 1000, 30000);
        setTimeout(refreshToken, refreshIn);
    }

    async function refreshToken() {
        try {
            const resp = await fetch('/auth/refresh', {
                method: 'POST',
                credentials: 'include'  // 携带 HttpOnly Refresh Cookie
            });
            if (resp.ok) {
                const data = await resp.json();
                window.__ACCESS_TOKEN__ = data.access_token;
                window.__TOKEN_EXPIRES_IN__ = data.expires_in;
                scheduleRefresh();
            } else {
                // Refresh 失败，跳转登录
                window.__ACCESS_TOKEN__ = null;
                if (location.pathname !== '/login') {
                    location.href = '/login';
                }
            }
        } catch (e) {
            console.error('Token refresh failed', e);
        }
    }

    window.logout = async function() {
        await fetch('/auth/logout', { method: 'POST', credentials: 'include' });
        window.__ACCESS_TOKEN__ = null;
        location.href = '/login';
    };

    // 启动自动刷新调度
    if (window.__ACCESS_TOKEN__) {
        scheduleRefresh();
    }
})();
