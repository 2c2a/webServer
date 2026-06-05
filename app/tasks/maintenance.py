"""
Maintenance 任务模块

定时维护任务，使用 Huey periodic_task 替代 Celery Beat
调度计划：
- cleanup_expired_sessions: 每天午夜
- cleanup_expired_provision_tokens: 每天午夜
- cleanup_unactivated_certificates: 每天午夜
- cleanup_orphan_cert_dirs: 每天午夜
- cleanup_expired_rdp_domains: 每10分钟
- cleanup_expired_initial_tokens: 每周
"""

import logging

from app.huey_config import crontab, huey

logger = logging.getLogger(__name__)


# ========== 每天午夜执行的清理任务 ==========

@huey.periodic_task(crontab(minute="0", hour="0"))
def scheduled_cleanup_expired_sessions():
    """每天午夜：清理过期活动会话"""
    from app.tasks.bootstrap import cleanup_expired_sessions
    try:
        result = cleanup_expired_sessions()
        logger.info(f"[定时任务] 清理过期会话: {result}")
    except Exception as e:
        logger.error(f"[定时任务] 清理过期会话失败: {e}")


@huey.periodic_task(crontab(minute="0", hour="0"))
def scheduled_cleanup_expired_provision_tokens():
    """每天午夜：清理过期证书配置令牌"""
    from app.tasks.bootstrap import cleanup_expired_provision_tokens
    try:
        cleanup_expired_provision_tokens()
        logger.info("[定时任务] 清理过期配置令牌完成")
    except Exception as e:
        logger.error(f"[定时任务] 清理过期配置令牌失败: {e}")


@huey.periodic_task(crontab(minute="0", hour="0"))
def scheduled_cleanup_unactivated_certificates():
    """每天午夜：清理未激活的证书"""
    from app.tasks.bootstrap import cleanup_unactivated_certificates
    try:
        cleanup_unactivated_certificates()
        logger.info("[定时任务] 清理未激活证书完成")
    except Exception as e:
        logger.error(f"[定时任务] 清理未激活证书失败: {e}")


@huey.periodic_task(crontab(minute="0", hour="0"))
def scheduled_cleanup_orphan_cert_dirs():
    """每天午夜：清理孤立证书目录"""
    from app.tasks.bootstrap import cleanup_orphan_cert_dirs
    try:
        cleanup_orphan_cert_dirs()
        logger.info("[定时任务] 清理孤立证书目录完成")
    except Exception as e:
        logger.error(f"[定时任务] 清理孤立证书目录失败: {e}")


# ========== 每10分钟执行的清理任务 ==========

@huey.periodic_task(crontab(minute="*/10"))
def scheduled_cleanup_expired_rdp_domains():
    """每10分钟：停用过期的 RDP 域名路由"""
    from app.tasks.operations import cleanup_expired_rdp_domains
    try:
        result = cleanup_expired_rdp_domains()
        logger.info(f"[定时任务] 清理过期RDP域名: {result}")
    except Exception as e:
        logger.error(f"[定时任务] 清理过期RDP域名失败: {e}")


# ========== 每周执行的清理任务 ==========

@huey.periodic_task(crontab(minute="0", hour="0", day_of_week="0"))
def scheduled_cleanup_expired_initial_tokens():
    """每周日午夜：清理过期的初始令牌"""
    from app.tasks.bootstrap import cleanup_expired_initial_tokens
    try:
        result = cleanup_expired_initial_tokens()
        logger.info(f"[定时任务] 清理过期初始令牌: {result}")
    except Exception as e:
        logger.error(f"[定时任务] 清理过期初始令牌失败: {e}")
