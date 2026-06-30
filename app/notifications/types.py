"""站内信类型、等级与图标映射常量。

type 对应设计稿过滤标签与图标分类，level 对应卡片图标背景色与色条。
图标使用 Lucide 风格的 SVG path（与 frontend_shell.html 内联 SVG 一致）。
"""
from __future__ import annotations


class NotificationType:
    SYSTEM = "system"
    TICKET = "ticket"
    POINTS = "points"
    SECURITY = "security"
    PRODUCT = "product"
    MAINTENANCE = "maintenance"


class NotificationLevel:
    INFO = "info"        # --c-info  蓝
    SUCCESS = "success"  # --c-success 绿
    WARNING = "warning"  # --c-warning 黄
    ERROR = "error"      # --c-error  红
    BRAND = "brand"      # --c-brand  品牌紫


# type → (默认图标 svg path, 默认 level, 图标背景色 alpha 0.1 时的色值)
# 图标 path 取自 Lucide（与 frontend_shell.html 风格一致）
TYPE_META: dict[str, tuple[str, str]] = {
    NotificationType.TICKET: (
        "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
        NotificationLevel.INFO,
    ),
    NotificationType.POINTS: (
        "M12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2",
        NotificationLevel.BRAND,
    ),
    NotificationType.SECURITY: (
        "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
        NotificationLevel.SUCCESS,
    ),
    NotificationType.PRODUCT: (
        "m7.5 4.27 9 5.15M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z",
        NotificationLevel.BRAND,
    ),
    NotificationType.MAINTENANCE: (
        "M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z",
        NotificationLevel.WARNING,
    ),
    NotificationType.SYSTEM: (
        "M22 17H2a3 3 0 0 0 3-3V9a7 7 0 0 1 14 0v5a3 3 0 0 0 3 3zm-8.27 4a2 2 0 0 1-3.46 0",
        NotificationLevel.INFO,
    ),
}


# 过滤标签列表（与设计稿圆角按钮对应）
# (filter_key, label) —— filter_key 同时用作 type 过滤值
FILTER_TABS: list[tuple[str, str]] = [
    ("all", "全部"),
    ("unread", "未读"),
    ("system", "系统"),
    ("ticket", "工单"),
]
