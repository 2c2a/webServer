"""keyed-BLAKE2b 缓存键与 ETag 生成。

策略：
- 页面骨架路由仅依据请求域名解析租户配置，绝不依赖用户状态
- 按域名区分并配合 keyed-BLAKE2b 签名生成缓存键，实现 CDN 边缘节点全量高速缓存与防污染
- HTMX ETag 同样用 keyed-BLAKE2b 生成，兼顾极速与防脏数据污染

缓存键结构：shell:{domain_hash}:{path_hash}
ETag 结构：W/"{blake2b_short}"
"""
from __future__ import annotations

from urllib.parse import urlencode

from app.security.crypto import keyed_blake2b, keyed_blake2b_short

# 缓存键前缀
SHELL_KEY_PREFIX = "shell"
FRAGMENT_KEY_PREFIX = "frag"
TENANT_KEY_PREFIX = "tenant"


def domain_hash(domain: str) -> str:
    """域名哈希（keyed-BLAKE2b），用于缓存键的域名维度。"""
    return keyed_blake2b_short(domain, context="domain")


def tenant_cache_key(hostname: str) -> str:
    """租户配置缓存键（按域名）。

    用于缓存域名 → SiteGroup 的解析结果，避免每次请求查库。
    """
    return f"{TENANT_KEY_PREFIX}:host:{keyed_blake2b_short(hostname, context='tenant')}"


def app_shell_cache_key(domain: str, path: str) -> str:
    """App Shell 边缘缓存键。

    仅依据域名 + 路径生成，绝不包含用户状态，确保 CDN 可全量缓存。
    """
    dh = domain_hash(domain)
    ph = keyed_blake2b_short(path, context="shell-path")
    return f"{SHELL_KEY_PREFIX}:{dh}:{ph}"


def fragment_cache_key(domain: str, path: str, params: dict | None = None) -> str:
    """HTMX 动态片段缓存键（按域名+路径+参数）。

    片段通常不缓存（动态内容），但某些半静态片段可短时缓存。
    """
    parts = [domain, path]
    if params:
        parts.append(urlencode(sorted(params.items()), doseq=True))
    raw = "|".join(parts)
    return f"{FRAGMENT_KEY_PREFIX}:{keyed_blake2b_short(raw, context='fragment')}"


def compute_etag(*parts: str) -> str:
    """计算 HTMX ETag（keyed-BLAKE2b 短哈希）。

    用于片段响应的 If-None-Match 校验，命中则返回 304。
    """
    raw = "|".join(parts)
    return f'W/"{keyed_blake2b_short(raw, context="etag")}"'


def cache_vary_headers() -> list[str]:
    """App Shell 响应的 Vary 头（仅域名相关，不含用户状态）。"""
    return ["Host"]


def edge_cache_headers(ttl: int) -> dict[str, str]:
    """生成 CDN 边缘缓存响应头。

    - Cache-Control: public, max-age（CDN 可缓存）
    - 不含 Set-Cookie（确保可缓存性）
    """
    return {
        "Cache-Control": f"public, max-age={ttl}, s-maxage={ttl}",
        "Vary": ", ".join(cache_vary_headers()),
        "X-2C2A-Cache": "shell",
    }


def no_cache_headers() -> dict[str, str]:
    """动态片段响应头（不可缓存）。"""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "X-2C2A-Cache": "fragment",
    }
