"""基于域名的租户解析。

策略（来自架构要求）：
- 页面骨架路由仅依据请求域名解析租户配置进行渲染，绝不依赖用户状态
- 通过按域名区分并配合 keyed-BLAKE2b 签名生成缓存键
- 解析结果缓存到 Redis（TTL 5 分钟），避免每次请求查库
- 未匹配域名时回退到默认租户（全局配置）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import tenant_cache_key
from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.tenant import SiteGroup, SiteGroupConfig, SiteGroupHostname

log = get_logger(__name__)


@dataclass
class TenantContext:
    """租户上下文：一次请求的租户解析结果。"""

    hostname: str
    site_group: Optional[SiteGroup] = None
    site_group_id: Optional[int] = None
    is_default: bool = True  # 是否回退到默认（全局）租户
    # 站点组是否标记为演示站点（SiteGroup.is_demo 的快照）
    site_is_demo: bool = False

    @property
    def display_name(self) -> str:
        if self.site_group and self.site_group.site_name:
            return self.site_group.site_name
        return settings.app_name

    @property
    def is_demo(self) -> bool:
        """当前请求是否处于演示模式。

        全局 settings.demo 是总闸；SiteGroup.is_demo 是单站点标记。
        两者同时为 True 时才视为演示站点。
        """
        return settings.demo and self.site_is_demo


async def resolve_tenant_by_hostname(
    db: AsyncSession, hostname: str
) -> TenantContext:
    """按域名解析租户。

    1. 先查 Redis 缓存（keyed-BLAKE2b 域名哈希键）
    2. 缓存未命中查 SiteGroupHostname 表
    3. 命中且 SiteGroup 激活则返回该租户，否则回退默认租户
    4. 结果写回缓存
    """
    hostname = hostname.split(":")[0].lower().strip()  # 去端口、小写
    cache_key = tenant_cache_key(hostname)

    # 尝试 Redis 缓存
    if settings.redis_enabled:
        try:
            redis = await get_redis()
            cached = await redis.get(cache_key)
            if cached is not None:
                if cached == "0":
                    return TenantContext(hostname=hostname, is_default=True)
                # 缓存格式 "id:is_demo"，兼容旧格式纯数字 "id"
                sg_id, _, is_demo_str = cached.partition(":")
                site_is_demo = is_demo_str == "1" if is_demo_str else False
                return TenantContext(
                    hostname=hostname,
                    site_group_id=int(sg_id),
                    is_default=False,
                    site_is_demo=site_is_demo,
                )
        except Exception as e:  # noqa: BLE001
            log.warning("tenant_cache_read_failed", error=str(e))

    # 查库
    result = await db.execute(
        select(SiteGroupHostname, SiteGroup)
        .join(SiteGroup, SiteGroupHostname.site_group_id == SiteGroup.id)
        .where(SiteGroupHostname.hostname == hostname)
        .where(SiteGroup.is_active == True)  # noqa: E712
    )
    row = result.first()

    if row is None:
        # 未匹配，缓存 0（默认租户）
        await _cache_tenant(cache_key, "0")
        return TenantContext(hostname=hostname, is_default=True)

    _sg_hostname, sg = row
    # 缓存格式 "id:is_demo"
    await _cache_tenant(cache_key, f"{sg.id}:{1 if sg.is_demo else 0}")
    return TenantContext(
        hostname=hostname,
        site_group=sg,
        site_group_id=sg.id,
        is_default=False,
        site_is_demo=sg.is_demo,
    )


async def _cache_tenant(cache_key: str, value: str) -> None:
    if not settings.redis_enabled:
        return
    try:
        redis = await get_redis()
        await redis.set(cache_key, value, ex=settings.tenant_cache_ttl)
    except Exception as e:  # noqa: BLE001
        log.warning("tenant_cache_write_failed", error=str(e))


async def invalidate_tenant_cache(hostname: str) -> None:
    """租户配置变更时清除缓存。"""
    if not settings.redis_enabled:
        return
    try:
        redis = await get_redis()
        await redis.delete(tenant_cache_key(hostname))
    except Exception as e:  # noqa: BLE001
        log.warning("tenant_cache_invalidate_failed", error=str(e))


async def get_effective_config(
    db: AsyncSession, tenant: TenantContext
) -> dict:
    """获取生效配置：站点组配置覆盖全局配置（非空字段优先）。"""
    # 全局 SystemConfig（单例 id=1）
    from app.models.tenant import SystemConfig

    sys_result = await db.execute(select(SystemConfig).where(SystemConfig.id == 1))
    sys_cfg = sys_result.scalar_one_or_none()

    sg_cfg = None
    if tenant.site_group_id:
        sg_result = await db.execute(
            select(SiteGroupConfig).where(
                SiteGroupConfig.site_group_id == tenant.site_group_id
            )
        )
        sg_cfg = sg_result.scalar_one_or_none()

    # 合并：站点组非空字段覆盖全局
    merged: dict = {}
    if sys_cfg:
        merged.update(_config_to_dict(sys_cfg))
    if sg_cfg:
        for k, v in _sg_config_to_dict(sg_cfg).items():
            if v is not None and v != "":
                merged[k] = v
    return merged


def _config_to_dict(cfg) -> dict:
    return {
        "smtp_host": cfg.smtp_host,
        "smtp_port": cfg.smtp_port,
        "smtp_encryption": cfg.smtp_encryption,
        "smtp_username": cfg.smtp_username,
        "smtp_from_email": cfg.smtp_from_email,
        "smtp_from_name": cfg.smtp_from_name,
        "captcha_provider": cfg.captcha_provider,
        "captcha_type": cfg.captcha_type,
        "enable_registration": cfg.enable_registration,
        "site_name": cfg.site_name,
        "site_icon": cfg.site_icon,
        "icp_number": cfg.icp_number,
        "police_number": cfg.police_number,
    }


def _sg_config_to_dict(cfg) -> dict:
    return {
        "smtp_host": cfg.smtp_host,
        "smtp_port": cfg.smtp_port,
        "smtp_encryption": cfg.smtp_encryption,
        "smtp_username": cfg.smtp_username,
        "smtp_from_email": cfg.smtp_from_email,
        "smtp_from_name": cfg.smtp_from_name,
        "captcha_provider": cfg.captcha_provider,
        "captcha_type": cfg.captcha_type,
        "enable_registration": cfg.enable_registration,
        "site_name": cfg.site_name,
        "site_icon": cfg.site_icon,
        "icp_number": cfg.icp_number,
        "police_number": cfg.police_number,
    }
