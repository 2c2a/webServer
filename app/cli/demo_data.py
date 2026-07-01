"""演示业务数据预置与清理。

在 demo 模式下，每次启动自动清理所有演示站点的业务数据并重建一份新的，
让后台列表页（主机/产品/工单/积分/公告等）有可视化内容。

设计要点：
- 单站点 demo：遍历所有 ``is_demo=True`` 的站点组清理/预置数据
- 清理范围：演示站点下的所有业务数据（含用户演示期间手动创建的）
- 全局 ``settings.demo`` 是总闸：关闭时即使 ``SiteGroup.is_demo=True`` 也不生效
- 幂等：清理 + 重建可重复执行
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from app.cli.utils import db_session
from app.core.logging import get_logger
from app.models.announcement import Announcement
from app.models.host import Host, HostGroup
from app.models.notification import Notification
from app.models.operations import AccountOpeningRequest, CloudComputerUser, Product, ProductGroup
from app.models.points import PointRecord, PointTask, UserPoints
from app.models.tenant import SiteGroup
from app.models.ticket import Ticket, TicketCategory
from app.models.user import User
from app.security.field_cipher import encrypt_field

log = get_logger(__name__)


async def clean_demo_business_data() -> dict:
    """清理所有演示站点的业务数据。

    清理策略：
    - 遍历所有 ``is_demo=True`` 的站点组，按 site_group_id 清理业务数据
    - 含用户演示期间手动创建的数据
    - 无 ``site_group_id`` 的表（如 ``TicketCategory``）：演示环境全清
    - 通过外键间接关联的表（``AccountOpeningRequest``/``CloudComputerUser``）：
      按演示账号 ID 清理
    - 保留：演示账号本身和演示站点组本身

    清理顺序遵守外键依赖（先删依赖方，再删被依赖方）。

    :returns: {"deleted": {表名: 数量}, "site_groups": [站点slug...]}
    """
    deleted: dict[str, int] = {}

    async with db_session() as session:
        demo_sgs = (
            await session.execute(select(SiteGroup).where(SiteGroup.is_demo == True))  # noqa: E712
        ).scalars().all()
        if not demo_sgs:
            return {"deleted": deleted, "site_groups": []}

        sg_ids = [sg.id for sg in demo_sgs]

        # 演示账号 ID 清单（用于清理无 site_group_id 但通过 user 关联的表）
        demo_user_ids = list(
            (
                await session.execute(
                    select(User.id).where(
                        User.username.in_(["superadmin", "siteadmin", "user"])
                    )
                )
            ).scalars()
        )

        # ── 1. 流水类（先删，避免余额/外键约束）──
        result = await session.execute(
            delete(PointRecord).where(PointRecord.site_group_id.in_(sg_ids))
        )
        deleted["point_record"] = result.rowcount or 0

        result = await session.execute(
            delete(Notification).where(Notification.site_group_id.in_(sg_ids))
        )
        deleted["notification"] = result.rowcount or 0

        # ── 2. 积分余额 ──
        result = await session.execute(
            delete(UserPoints).where(UserPoints.site_group_id.in_(sg_ids))
        )
        deleted["user_points"] = result.rowcount or 0

        # ── 3. 积分任务 ──
        result = await session.execute(
            delete(PointTask).where(PointTask.site_group_id.in_(sg_ids))
        )
        deleted["point_task"] = result.rowcount or 0

        # ── 4. 工单（CASCADE 会自动清理 Comment/Activity/Attachment）──
        result = await session.execute(
            delete(Ticket).where(Ticket.site_group_id.in_(sg_ids))
        )
        deleted["ticket"] = result.rowcount or 0

        # ── 5. 工单分类（无 site_group_id，演示环境全清）──
        result = await session.execute(delete(TicketCategory))
        deleted["ticket_category"] = result.rowcount or 0

        # ── 6. 公告 ──
        result = await session.execute(
            delete(Announcement).where(Announcement.site_group_id.in_(sg_ids))
        )
        deleted["announcement"] = result.rowcount or 0

        # ── 7. 开户申请（无 site_group_id，通过 applicant_id 清理）──
        if demo_user_ids:
            result = await session.execute(
                delete(AccountOpeningRequest).where(
                    AccountOpeningRequest.applicant_id.in_(demo_user_ids)
                )
            )
            deleted["account_opening_request"] = result.rowcount or 0

        # ── 8. 云电脑用户（无 site_group_id，通过 owner_id 清理）──
        if demo_user_ids:
            result = await session.execute(
                delete(CloudComputerUser).where(
                    CloudComputerUser.owner_id.in_(demo_user_ids)
                )
            )
            deleted["cloud_computer_user"] = result.rowcount or 0

        # ── 9. 产品（必须在 Host 之前，因 Product.host_id 是 CASCADE）──
        result = await session.execute(
            delete(Product).where(Product.site_group_id.in_(sg_ids))
        )
        deleted["product"] = result.rowcount or 0

        # ── 10. 产品组 ──
        result = await session.execute(
            delete(ProductGroup).where(ProductGroup.site_group_id.in_(sg_ids))
        )
        deleted["product_group"] = result.rowcount or 0

        # ── 11. 主机组 ──
        result = await session.execute(
            delete(HostGroup).where(HostGroup.site_group_id.in_(sg_ids))
        )
        deleted["host_group"] = result.rowcount or 0

        # ── 12. 主机（最后清理）──
        result = await session.execute(
            delete(Host).where(Host.site_group_id.in_(sg_ids))
        )
        deleted["host"] = result.rowcount or 0

    log.info("demo_data_cleaned", deleted=deleted, site_groups=[sg.slug for sg in demo_sgs])
    return {"deleted": deleted, "site_groups": [sg.slug for sg in demo_sgs]}


async def seed_demo_business_data() -> dict:
    """预置演示业务数据。

    遍历所有 ``is_demo=True`` 的站点组，为每个演示站点预置业务数据。
    前置条件：演示账号与演示站点组已存在（由 ``seed_demo_accounts()`` 创建）。

    :returns: {"created": {表名: 数量}, "site_groups": [站点slug...]}
    """
    created: dict[str, int] = {}
    seeded_sgs: list[str] = []

    async with db_session() as session:
        demo_sgs = (
            await session.execute(select(SiteGroup).where(SiteGroup.is_demo == True))  # noqa: E712
        ).scalars().all()
        if not demo_sgs:
            return {"created": created, "site_groups": []}

        # 演示账号（全局共享，不按站点隔离）
        superadmin = (
            await session.execute(select(User).where(User.username == "superadmin"))
        ).scalar_one_or_none()
        siteadmin = (
            await session.execute(select(User).where(User.username == "siteadmin"))
        ).scalar_one_or_none()
        normal_user = (
            await session.execute(select(User).where(User.username == "user"))
        ).scalar_one_or_none()
        if not all([superadmin, siteadmin, normal_user]):
            raise RuntimeError("演示账号不存在，请先运行 2c2a account demo-seed")

        # 为每个演示站点预置数据
        for demo_sg in demo_sgs:
            sg_count = await _seed_for_site_group(
                session, demo_sg, superadmin, siteadmin, normal_user
            )
            for table, count in sg_count.items():
                created[table] = created.get(table, 0) + count
            seeded_sgs.append(demo_sg.slug)

    log.info("demo_data_seeded", created=created, site_groups=seeded_sgs)
    return {"created": created, "site_groups": seeded_sgs}


async def _seed_for_site_group(
    session, demo_sg: SiteGroup, superadmin: User, siteadmin: User, normal_user: User
) -> dict[str, int]:
    """为单个演示站点预置业务数据。返回 {表名: 数量}。"""
    created: dict[str, int] = {}
    sg_id = demo_sg.id

    # ── 1. Host ──
    hosts: list[Host] = []
    host_specs = [
        {
            "name": "办公云主机-01",
            "hostname": "10.0.1.10",
            "os_version": "Windows Server 2022",
            "description": "北京机房 · 办公云主节点",
        },
        {
            "name": "设计云主机-02",
            "hostname": "10.0.1.11",
            "os_version": "Windows Server 2019",
            "description": "上海机房 · 设计渲染节点",
        },
    ]
    for spec in host_specs:
        host = Host(
            name=spec["name"],
            os_type="windows",
            hostname=spec["hostname"],
            connection_type="winrm",
            auth_method="ntlm",
            port=5985,
            rdp_port=3389,
            use_ssl=False,
            username="administrator",
            password_cipher=encrypt_field("Demo@2026", field_name="host_password"),
            os_version=spec["os_version"],
            status="active",
            description=spec["description"],
            created_by_id=superadmin.id,
            site_group_id=sg_id,
        )
        session.add(host)
        hosts.append(host)
    await session.flush()
    created["host"] = len(hosts)

    # ── 2. HostGroup ──
    host_group = HostGroup(
        name="演示主机组",
        description="包含所有演示主机的分组",
        created_by_id=superadmin.id,
        site_group_id=sg_id,
    )
    session.add(host_group)
    await session.flush()
    created["host_group"] = 1

    # ── 3. ProductGroup ──
    product_groups: list[ProductGroup] = []
    pg_specs = [
        {"name": "标准办公云", "description": "适合日常办公的云电脑产品"},
        {"name": "专业设计云", "description": "适合设计渲染的高性能云电脑"},
    ]
    for spec in pg_specs:
        pg = ProductGroup(
            name=spec["name"],
            description=spec["description"],
            display_order=0,
            is_active=True,
            visibility="public",
            site_group_id=sg_id,
            created_by_id=superadmin.id,
        )
        session.add(pg)
        product_groups.append(pg)
    await session.flush()
    created["product_group"] = len(product_groups)

    # ── 4. Product ──
    products: list[Product] = []
    product_specs = [
        {
            "name": "办公标准版",
            "display_name": "办公标准版 · 4核8G",
            "description": "4 核 CPU / 8GB 内存 / 100GB 系统盘",
            "host": hosts[0],
            "product_group": product_groups[0],
            "required_points": 0,
            "terms": "本产品仅供演示使用，禁止存储真实数据。",
        },
        {
            "name": "办公专业版",
            "display_name": "办公专业版 · 8核16G",
            "description": "8 核 CPU / 16GB 内存 / 200GB 系统盘",
            "host": hosts[0],
            "product_group": product_groups[0],
            "required_points": 100,
            "terms": "",
        },
        {
            "name": "设计渲染版",
            "display_name": "设计渲染版 · 16核32G",
            "description": "16 核 CPU / 32GB 内存 / 500GB 系统盘 + GPU",
            "host": hosts[1],
            "product_group": product_groups[1],
            "required_points": 500,
            "terms": "本产品仅供演示使用，关闭后数据将丢失。",
        },
    ]
    for spec in product_specs:
        product = Product(
            name=spec["name"],
            description=spec["description"],
            display_name=spec["display_name"],
            display_description=spec["description"],
            product_group_id=spec["product_group"].id,
            host_id=spec["host"].id,
            site_group_id=sg_id,
            rdp_port=3389,
            display_hostname=spec["host"].hostname,
            is_available=True,
            auto_approval=False,
            visibility="public",
            limit_one_per_user=True,
            required_points=spec["required_points"],
            terms=spec["terms"] or None,
            created_by_id=superadmin.id,
        )
        session.add(product)
        products.append(product)
    await session.flush()
    created["product"] = len(products)

    # ── 5. TicketCategory ──
    categories: list[TicketCategory] = []
    cat_specs = [
        {"name": "技术咨询", "icon": "help-circle", "priority": "normal"},
        {"name": "故障报修", "icon": "alert-triangle", "priority": "high"},
        {"name": "账户问题", "icon": "user", "priority": "normal"},
    ]
    for spec in cat_specs:
        cat = TicketCategory(
            name=spec["name"],
            description=f"演示分类：{spec['name']}",
            icon=spec["icon"],
            default_priority=spec["priority"],
            sla_hours=24,
            is_active=True,
            display_order=0,
            created_by_id=superadmin.id,
        )
        session.add(cat)
        categories.append(cat)
    await session.flush()
    created["ticket_category"] = len(categories)

    # ── 6. Ticket ──
    tickets: list[Ticket] = []
    now = datetime.now(timezone.utc)
    ticket_specs = [
        {
            "title": "无法连接到办公云电脑",
            "description": "使用 RDP 连接办公标准版时提示凭据错误，已确认密码正确。",
            "category": categories[1],  # 故障报修
            "status": "open",
            "priority": "high",
            "creator": normal_user,
            "assignee": siteadmin,
        },
        {
            "title": "申请增加磁盘配额",
            "description": "设计渲染版默认 500GB 不够用，希望增加到 1TB。",
            "category": categories[0],  # 技术咨询
            "status": "pending",
            "priority": "normal",
            "creator": normal_user,
            "assignee": siteadmin,
        },
        {
            "title": "忘记登录密码",
            "description": "演示账号 user 忘记密码，请求重置。",
            "category": categories[2],  # 账户问题
            "status": "resolved",
            "priority": "normal",
            "creator": normal_user,
            "assignee": siteadmin,
            "resolved_at": now - timedelta(days=1),
        },
    ]
    for i, spec in enumerate(ticket_specs, start=1):
        ticket = Ticket(
            ticket_no=f"TK-DEMO{i:06d}",
            title=spec["title"],
            description=spec["description"],
            category_id=spec["category"].id,
            status=spec["status"],
            priority=spec["priority"],
            source="web",
            creator_id=spec["creator"].id,
            assignee_id=spec["assignee"].id if spec.get("assignee") else None,
            due_at=now + timedelta(days=2) if spec["status"] != "resolved" else None,
            resolved_at=spec.get("resolved_at"),
            closed_at=spec.get("resolved_at") if spec["status"] == "resolved" else None,
            site_group_id=sg_id,
        )
        session.add(ticket)
        tickets.append(ticket)
    await session.flush()
    created["ticket"] = len(tickets)

    # ── 7. Announcement ──
    announcements: list[Announcement] = []
    ann_specs = [
        {
            "title": "欢迎使用 2c2a 演示系统",
            "content": "本系统为演示环境，所有数据每次重启后会被重置。\n\n您可以自由体验各项功能，如有疑问请联系管理员。",
            "is_pinned": True,
            "sort_order": 100,
        },
        {
            "title": "系统维护通知",
            "content": "演示系统将于每周日凌晨 3:00-5:00 进行维护，期间可能无法访问。",
            "is_pinned": False,
            "sort_order": 50,
        },
    ]
    for spec in ann_specs:
        ann = Announcement(
            title=spec["title"],
            content=spec["content"],
            is_pinned=spec["is_pinned"],
            is_active=True,
            sort_order=spec["sort_order"],
            published_at=now,
            created_by_id=superadmin.id,
            site_group_id=sg_id,
        )
        session.add(ann)
        announcements.append(ann)
    await session.flush()
    created["announcement"] = len(announcements)

    # ── 8. PointTask ──
    tasks: list[PointTask] = []
    task_specs = [
        {
            "name": "每日签到",
            "description": "每天首次登录自动获得积分",
            "method": "daily_checkin",
            "points": 10,
            "config": None,
        },
        {
            "name": "提交工单",
            "description": "每提交一个工单获得积分（上限 100）",
            "method": "ticket_submit",
            "points": 5,
            "config": None,
        },
        {
            "name": "完善资料",
            "description": "首次完善个人资料获得积分",
            "method": "profile_complete",
            "points": 50,
            "config": None,
        },
    ]
    for spec in task_specs:
        task = PointTask(
            name=spec["name"],
            description=spec["description"],
            detection_method=spec["method"],
            points=spec["points"],
            is_active=True,
            config=spec["config"],
            site_group_id=sg_id,
            created_by_id=superadmin.id,
        )
        session.add(task)
        tasks.append(task)
    await session.flush()
    created["point_task"] = len(tasks)

    # ── 9. UserPoints + PointRecord ──
    user_points = UserPoints(
        user_id=normal_user.id,
        site_group_id=sg_id,
        balance=160,  # 50(资料) + 10(签到) + 100(管理员赠送)
    )
    session.add(user_points)

    records_spec = [
        {"delta": 50, "balance_after": 50, "source": "task", "task": tasks[2], "desc": "完善个人资料"},
        {"delta": 10, "balance_after": 60, "source": "task", "task": tasks[0], "desc": "每日签到"},
        {"delta": 100, "balance_after": 160, "source": "admin", "task": None, "desc": "管理员赠送演示积分"},
    ]
    for spec in records_spec:
        record = PointRecord(
            user_id=normal_user.id,
            delta=spec["delta"],
            balance_after=spec["balance_after"],
            source=spec["source"],
            task_id=spec["task"].id if spec["task"] else None,
            description=spec["desc"],
            site_group_id=sg_id,
        )
        session.add(record)
    created["user_points"] = 1
    created["point_record"] = len(records_spec)

    return created


async def reset_demo_business_data() -> dict:
    """清理并重建演示业务数据（原子操作）。"""
    cleaned = await clean_demo_business_data()
    seeded = await seed_demo_business_data()
    return {"cleaned": cleaned, "seeded": seeded}
