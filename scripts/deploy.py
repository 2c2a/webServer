#!/usr/bin/env python3
"""
ZASCA 交互式部署脚本
根据部署环境动态生成 pyproject.toml，仅安装所需依赖，避免冗余库

用法:
    python3 scripts/deploy.py
"""

import sys
import shutil
import subprocess
import curses
from pathlib import Path
import secrets
import string
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent

DEPS_CORE = {
    "Django": "Django==4.2.27",
    "djangorestframework": "djangorestframework==3.15.2",
    "django-cors-headers": "django-cors-headers==4.3.1",
    "django-cotton": "django-cotton @ git+https://github.com/2c2a/django-cotton.git@feature/x-prefix-tag-support",
    "django-formtools": "django-formtools>=2.5.1",
    "python-dotenv": "python-dotenv==1.2.1",
    "PyJWT": "PyJWT>=2.8.0",
    "cryptography": "cryptography==46.0.3",
    "requests": "requests==2.32.3",
    "pillow": "pillow==12.1.0",
    "toml": "toml",
}

DEPS_CELERY = {
    "celery": "celery==5.4.0",
}

DEPS_MYSQL = {
    "pymysql": "pymysql>=1.1.2",
}

DEPS_POSTGRESQL = {
    "psycopg": "psycopg[binary]>=3.0",
}

DEPS_REDIS = {
    "redis": "redis>=5.0.0",
}

DEPS_SQLITE_BROKER = {
    "sqlalchemy": "sqlalchemy>=2.0.0",
}

DEPS_WINRM = {
    "pywinrm": "pywinrm==0.4.3",
}

DEPS_KERBEROS = {
    "gssapi": "gssapi>=1.11.1",
    "krb5": "krb5>=0.9.0",
}

DEPS_MARKDOWN = {
    "Markdown": "Markdown==3.10.1",
}

DEPS_2FA = {
    "pyotp": "pyotp",
}

DEPS_DEV = {
    "pytest": "pytest",
    "pytest-django": "pytest-django",
    "black": "black",
    "flake8": "flake8",
    "django-stubs": "django-stubs>=6.0.2",
    "pyrefly": "pyrefly>=0.60.0",
}

DB_OPTIONS = [
    ("sqlite", "SQLite", "零配置本地文件数据库，适合开发/小规模部署"),
    ("mysql", "MySQL / MariaDB", "生产级关系数据库，适合中大规模部署"),
    ("postgresql", "PostgreSQL", "生产级关系数据库，功能最丰富"),
]

FEATURE_OPTIONS = [
    ("celery", "Celery 异步任务队列", "后台任务处理（主机操作、工单通知等）", True),
    ("redis", "Redis 缓存/消息队列", "高性能缓存、会话存储、Celery Broker", False),
    ("winrm", "WinRM Windows 远程管理", "远程管理 Windows 服务器", False),
    ("kerberos", "Kerberos 域认证", "Windows 域环境集成认证", False),
    ("markdown", "Markdown 渲染", "仪表盘/工单中的 Markdown 内容渲染", True),
    ("2fa", "双因素认证 (TOTP)", "基于时间的一次性密码二次验证", True),
]

DEV_OPTION = ("dev", "开发/测试工具", "pytest, black, flake8, django-stubs 等", False)

C_TITLE = 1
C_SUBTITLE = 2
C_HIGHLIGHT = 3
C_SELECTED = 4
C_UNSELECTED = 5
C_RADIO_ON = 6
C_RADIO_OFF = 7
C_CHECK_ON = 8
C_CHECK_OFF = 9
C_DESC = 10
C_HINT = 11
C_BORDER = 12
C_SUCCESS = 13
C_WARN = 14
C_ERROR = 15
C_DEP = 16
C_DEP_DEV = 17
C_BANNER = 18


def _safe_addstr(stdscr, y, x, text, attr=0):
    max_y, max_x = stdscr.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    available = max_x - x - 1
    if available <= 0:
        return
    text = text[:available]
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def _init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_TITLE, curses.COLOR_CYAN, -1)
    curses.init_pair(C_SUBTITLE, curses.COLOR_WHITE, -1)
    curses.init_pair(C_HIGHLIGHT, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(C_SELECTED, curses.COLOR_CYAN, -1)
    curses.init_pair(C_UNSELECTED, curses.COLOR_WHITE, -1)
    curses.init_pair(C_RADIO_ON, curses.COLOR_GREEN, -1)
    curses.init_pair(C_RADIO_OFF, curses.COLOR_WHITE, -1)
    curses.init_pair(C_CHECK_ON, curses.COLOR_GREEN, -1)
    curses.init_pair(C_CHECK_OFF, curses.COLOR_WHITE, -1)
    curses.init_pair(C_DESC, 8, -1)
    curses.init_pair(C_HINT, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_BORDER, curses.COLOR_CYAN, -1)
    curses.init_pair(C_SUCCESS, curses.COLOR_GREEN, -1)
    curses.init_pair(C_WARN, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_ERROR, curses.COLOR_RED, -1)
    curses.init_pair(C_DEP, curses.COLOR_GREEN, -1)
    curses.init_pair(C_DEP_DEV, curses.COLOR_YELLOW, -1)
    curses.init_pair(C_BANNER, curses.COLOR_CYAN, -1)


def _draw_banner(stdscr, y, max_x):
    title = " ZASCA 交互式部署管理脚本 "
    x = max(0, (max_x - len(title)) // 2)
    _safe_addstr(stdscr, y, x, title, curses.color_pair(C_BANNER) | curses.A_BOLD)


def _draw_box(stdscr, y, x, h, w):
    _safe_addstr(stdscr, y, x, "┌" + "─" * (w - 2) + "┐", curses.color_pair(C_BORDER))
    for i in range(1, h - 1):
        _safe_addstr(stdscr, y + i, x, "│", curses.color_pair(C_BORDER))
        _safe_addstr(stdscr, y + i, x + w - 1, "│", curses.color_pair(C_BORDER))
    _safe_addstr(stdscr, y + h - 1, x, "└" + "─" * (w - 2) + "┘", curses.color_pair(C_BORDER))


def _draw_radio_item(stdscr, y, x, selected, active, label, desc, max_w):
    if selected:
        marker = "◉"
        m_color = C_RADIO_ON | curses.A_BOLD
    else:
        marker = "○"
        m_color = C_RADIO_OFF

    if active:
        bg = curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD
        _safe_addstr(stdscr, y, x, f"  {marker} {label}", bg)
    else:
        _safe_addstr(stdscr, y, x, "  ", curses.color_pair(C_UNSELECTED))
        _safe_addstr(stdscr, y, x + 2, marker, curses.color_pair(m_color))
        _safe_addstr(stdscr, y, x + 4, label, curses.color_pair(C_SELECTED if selected else C_UNSELECTED) | curses.A_BOLD)

    if desc:
        desc_x = x + 6
        remaining = max_w - (desc_x - x) - 1
        if remaining > 3:
            _safe_addstr(stdscr, y + 1, desc_x, desc[:remaining], curses.color_pair(C_DESC) if not active else curses.color_pair(C_HIGHLIGHT))


def _draw_check_item(stdscr, y, x, checked, active, label, desc, max_w):
    if checked:
        marker = "☑"
        m_color = C_CHECK_ON | curses.A_BOLD
    else:
        marker = "☐"
        m_color = C_CHECK_OFF

    if active:
        bg = curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD
        _safe_addstr(stdscr, y, x, f"  {marker} {label}", bg)
    else:
        _safe_addstr(stdscr, y, x, "  ", curses.color_pair(C_UNSELECTED))
        _safe_addstr(stdscr, y, x + 2, marker, curses.color_pair(m_color))
        _safe_addstr(stdscr, y, x + 4, label, curses.color_pair(C_SELECTED if checked else C_UNSELECTED) | curses.A_BOLD)

    if desc:
        desc_x = x + 6
        remaining = max_w - (desc_x - x) - 1
        if remaining > 3:
            _safe_addstr(stdscr, y + 1, desc_x, desc[:remaining], curses.color_pair(C_DESC) if not active else curses.color_pair(C_HIGHLIGHT))


def _draw_hint(stdscr, y, x, hint_text):
    _safe_addstr(stdscr, y, x, hint_text, curses.color_pair(C_HINT))


def _page_db(stdscr, selected):
    _init_colors()
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()
    box_w = min(72, max_x - 4)
    box_h = 5 + len(DB_OPTIONS) * 3
    box_x = max(0, (max_x - box_w) // 2)
    box_y = 2

    _draw_banner(stdscr, 0, max_x)
    _draw_box(stdscr, box_y, box_x, box_h, box_w)

    title = " 数据库引擎 (单选) "
    tx = box_x + max(0, (box_w - len(title)) // 2)
    _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

    for i, (key, label, desc) in enumerate(DB_OPTIONS):
        iy = box_y + 2 + i * 3
        _draw_radio_item(stdscr, iy, box_x + 2, i == selected, i == selected, label, desc, box_w - 4)

    hint_y = box_y + box_h + 1
    _draw_hint(stdscr, hint_y, box_x + 2, "↑↓ 移动  Enter 确认  Esc 退出")

    stdscr.refresh()


def _select_db(stdscr):
    selected = 0
    while True:
        _page_db(stdscr, selected)
        key = stdscr.getch()
        if key == curses.KEY_UP:
            selected = (selected - 1) % len(DB_OPTIONS)
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % len(DB_OPTIONS)
        elif key in (curses.KEY_ENTER, 10, 13):
            return DB_OPTIONS[selected][0]
        elif key == 27:
            return None
        elif key in (ord('1'), ord('2'), ord('3')):
            idx = key - ord('1')
            if 0 <= idx < len(DB_OPTIONS):
                return DB_OPTIONS[idx][0]


def _page_features(stdscr, cursor, features_state, dev_state, page):
    _init_colors()
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    if page == 0:
        items = FEATURE_OPTIONS
        total = len(items)
        box_w = min(76, max_x - 4)
        box_h = 5 + total * 3
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = " 功能模块 (多选) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        for i, (key, label, desc, default) in enumerate(items):
            iy = box_y + 2 + i * 3
            _draw_check_item(stdscr, iy, box_x + 2, features_state[key], i == cursor, label, desc, box_w - 4)

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "↑↓ 移动  Space 切换  Enter 下一步  Esc 返回")
    else:
        box_w = min(76, max_x - 4)
        box_h = 7
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = " 开发环境 "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        key, label, desc, default = DEV_OPTION
        iy = box_y + 2
        _draw_check_item(stdscr, iy, box_x + 2, dev_state, True, label, desc, box_w - 4)

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "Space 切换  Enter 确认  Esc 返回")

    stdscr.refresh()


def _select_features(stdscr):
    features_state = {key: default for key, _, _, default in FEATURE_OPTIONS}
    dev_state = DEV_OPTION[3]
    cursor = 0
    page = 0

    while True:
        _page_features(stdscr, cursor, features_state, dev_state, page)
        key = stdscr.getch()

        if page == 0:
            if key == curses.KEY_UP:
                cursor = (cursor - 1) % len(FEATURE_OPTIONS)
            elif key == curses.KEY_DOWN:
                cursor = (cursor + 1) % len(FEATURE_OPTIONS)
            elif key == ord(' '):
                fk = FEATURE_OPTIONS[cursor][0]
                features_state[fk] = not features_state[fk]
            elif key in (curses.KEY_ENTER, 10, 13):
                page = 1
                cursor = 0
            elif key == 27:
                return None
        else:
            if key == ord(' '):
                dev_state = not dev_state
            elif key in (curses.KEY_ENTER, 10, 13):
                return features_state, dev_state
            elif key == 27:
                page = 0
                cursor = 0


def _page_summary(stdscr, answers, deps, dev_deps, cursor, scroll=0):
    _init_colors()
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    db_names = {"sqlite": "SQLite", "mysql": "MySQL / MariaDB", "postgresql": "PostgreSQL"}
    feature_names = {
        "celery": "Celery",
        "redis": "Redis",
        "winrm": "WinRM",
        "kerberos": "Kerberos",
        "markdown": "Markdown",
        "2fa": "2FA",
    }

    lines = []
    lines.append(("title", " 部署摘要 "))
    lines.append(("blank", ""))
    lines.append(("kv", f"  数据库:     {db_names[answers['db']]}"))

    active_features = [feature_names[k] for k in ("celery", "redis", "winrm", "kerberos", "markdown", "2fa") if answers.get(k)]
    if active_features:
        lines.append(("kv", f"  功能模块:   {', '.join(active_features)}"))
    else:
        lines.append(("kv", "  功能模块:   无（仅核心框架）"))

    if answers.get("dev"):
        lines.append(("kv", "  开发工具:   已启用"))
    else:
        lines.append(("kv", "  开发工具:   未启用"))

    lines.append(("blank", ""))
    lines.append(("dep_title", f"  生产依赖 ({len(deps)} 个):"))
    for name, spec in deps.items():
        lines.append(("dep", f"    + {spec}"))

    if dev_deps:
        lines.append(("blank", ""))
        lines.append(("dep_dev_title", f"  开发依赖 ({len(dev_deps)} 个):"))
        for name, spec in dev_deps.items():
            lines.append(("dep_dev", f"    + {spec}"))

    total = len(deps) + len(dev_deps)
    lines.append(("blank", ""))
    lines.append(("total", f"  合计: {total} 个直接依赖（传递依赖由 uv 自动解析）"))

    box_w = min(76, max_x - 4)
    box_h = min(len(lines) + 4, max_y - 6)
    box_x = max(0, (max_x - box_w) // 2)
    box_y = 1

    _draw_banner(stdscr, 0, max_x)
    _draw_box(stdscr, box_y, box_x, box_h, box_w)

    max_visible = box_h - 3
    total_lines = len(lines)
    max_scroll = max(0, total_lines - max_visible)
    scroll = min(scroll, max_scroll)
    scroll = max(0, scroll)

    visible = lines[scroll:scroll + max_visible]
    for i, (kind, text) in enumerate(visible):
        ry = box_y + 1 + i
        rx = box_x + 2
        remaining = box_w - 5
        t = text[:remaining]

        if kind == "title":
            tx = box_x + max(0, (box_w - len(t)) // 2)
            _safe_addstr(stdscr, ry, tx, t, curses.color_pair(C_TITLE) | curses.A_BOLD)
        elif kind == "blank":
            pass
        elif kind == "kv":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_SUBTITLE) | curses.A_BOLD)
        elif kind == "dep_title":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_DEP) | curses.A_BOLD)
        elif kind == "dep":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_DEP))
        elif kind == "dep_dev_title":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_DEP_DEV) | curses.A_BOLD)
        elif kind == "dep_dev":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_DEP_DEV))
        elif kind == "total":
            _safe_addstr(stdscr, ry, rx, t, curses.color_pair(C_TITLE) | curses.A_BOLD)

    if max_scroll > 0:
        scroll_info = f" [{scroll + 1}-{min(scroll + max_visible, total_lines)}/{total_lines}] "
        _safe_addstr(stdscr, box_y + box_h - 2, box_x + box_w - len(scroll_info) - 2, scroll_info, curses.color_pair(C_DESC))

    btn_y = box_y + box_h + 1
    btn_labels = ["[✔ 确认生成]", "[✘ 取消]"]
    btn_x = box_x + 4
    for i, label in enumerate(btn_labels):
        if i == cursor:
            _safe_addstr(stdscr, btn_y, btn_x, label, curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD)
        else:
            _safe_addstr(stdscr, btn_y, btn_x, label, curses.color_pair(C_UNSELECTED))
        btn_x += len(label) + 3

    hint_y = btn_y + 2
    hint = "←→ 选择  Enter 确认  Esc 返回"
    if max_scroll > 0:
        hint = "↑↓ 滚动  " + hint
    _draw_hint(stdscr, hint_y, box_x + 2, hint)

    stdscr.refresh()
    return scroll


def _confirm_summary(stdscr, answers, deps, dev_deps):
    cursor = 0
    scroll = 0
    while True:
        scroll = _page_summary(stdscr, answers, deps, dev_deps, cursor, scroll)
        key = stdscr.getch()
        if key == curses.KEY_LEFT:
            cursor = 0
        elif key == curses.KEY_RIGHT:
            cursor = 1
        elif key == curses.KEY_UP:
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN:
            scroll += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return cursor == 0
        elif key == 27:
            return None
        elif key == ord('1'):
            return True
        elif key == ord('2'):
            return False


def _page_progress(stdscr, step, total_steps, message):
    _init_colors()
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    _draw_banner(stdscr, 0, max_x)

    box_w = min(60, max_x - 4)
    box_h = 5
    box_x = max(0, (max_x - box_w) // 2)
    box_y = 3

    _draw_box(stdscr, box_y, box_x, box_h, box_w)

    title = f" Step {step}/{total_steps} "
    tx = box_x + max(0, (box_w - len(title)) // 2)
    _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

    msg_x = box_x + 3
    _safe_addstr(stdscr, box_y + 2, msg_x, message[:box_w - 6], curses.color_pair(C_SUBTITLE))

    stdscr.refresh()


def _page_result(stdscr, success, answers, backup_name=None, env_configured=False, env_backup_name=None, migrate_success=False):
    _init_colors()
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    _draw_banner(stdscr, 0, max_x)

    box_w = min(72, max_x - 4)
    box_x = max(0, (max_x - box_w) // 2)
    box_y = 2

    if success:
        title = " ✔ 部署完成 "
        steps = []
        n = 1
        if env_configured:
            steps.append(f"{n}. .env 已配置              (可手动编辑调整)")
        else:
            steps.append(f"{n}. 配置 .env 文件          (参考 .env.example)")
        n += 1
        if migrate_success:
            steps.append(f"{n}. 数据库迁移              已完成")
        else:
            steps.append(f"{n}. 初始化数据库            uv run python manage.py migrate")
        n += 1
        steps.append(f"{n}. 创建管理员              uv run python manage.py createsuperuser")
        n += 1
        steps.append(f"{n}. 启动服务                uv run python manage.py runserver")
        if answers.get("celery"):
            n += 1
            steps.append(f"{n}. 启动 Celery             uv run celery -A config worker -l info")

        box_h = 4 + len(steps) + (2 if not answers.get("redis") and answers.get("celery") else 0) + (1 if backup_name else 0) + (1 if env_backup_name else 0)
        box_h = max(box_h, 8)

        _draw_box(stdscr, box_y, box_x, box_h, box_w)
        _safe_addstr(stdscr, box_y, box_x + max(0, (box_w - len(title)) // 2), title, curses.color_pair(C_SUCCESS) | curses.A_BOLD)

        for i, step in enumerate(steps):
            ry = box_y + 2 + i
            _safe_addstr(stdscr, ry, box_x + 3, step[:box_w - 6], curses.color_pair(C_SUBTITLE))

        row = box_y + 2 + len(steps)
        if not answers.get("redis") and answers.get("celery"):
            _safe_addstr(stdscr, row, box_x + 3, "⚠ Celery 使用 SQLite Broker，生产环境建议启用 Redis", curses.color_pair(C_WARN))
            row += 2

        if backup_name:
            _safe_addstr(stdscr, row, box_x + 3, f"备份: {backup_name}", curses.color_pair(C_DESC))
            row += 1
        if env_backup_name:
            _safe_addstr(stdscr, row, box_x + 3, f".env 备份: {env_backup_name}", curses.color_pair(C_DESC))
    else:
        box_h = 8
        _draw_box(stdscr, box_y, box_x, box_h, box_w)
        title = " ✘ 部署失败 "
        _safe_addstr(stdscr, box_y, box_x + max(0, (box_w - len(title)) // 2), title, curses.color_pair(C_ERROR) | curses.A_BOLD)
        _safe_addstr(stdscr, box_y + 2, box_x + 3, "依赖同步失败，请检查错误信息", curses.color_pair(C_ERROR))
        if backup_name:
            _safe_addstr(stdscr, box_y + 4, box_x + 3, f"恢复: cp {backup_name} pyproject.toml", curses.color_pair(C_WARN))

    hint_y = box_y + box_h + 1
    _draw_hint(stdscr, hint_y, box_x + 2, "按任意键退出")

    stdscr.refresh()
    stdscr.getch()


def _tui_main(stdscr):
    curses.curs_set(0)
    curses.noecho()
    stdscr.keypad(True)
    _init_colors()

    db = _select_db(stdscr)
    if db is None:
        return

    result = _select_features(stdscr)
    if result is None:
        return
    features_state, dev_state = result

    answers = {"db": db}
    answers.update(features_state)
    answers["dev"] = dev_state

    deps, dev_deps = compute_dependencies(answers)

    confirmed = _confirm_summary(stdscr, answers, deps, dev_deps)
    if confirmed is None or not confirmed:
        return

    toml_path = BASE_DIR / "pyproject.toml"
    backup = backup_file(toml_path)
    backup_name = backup.name if backup else None

    _page_progress(stdscr, 1, 3, "正在生成 pyproject.toml ...")
    content = generate_pyproject_toml(answers, deps, dev_deps)
    toml_path.write_text(content, encoding="utf-8")

    _page_progress(stdscr, 2, 3, "正在执行 uv sync ...")
    try:
        proc = subprocess.run(
            ["uv", "sync"],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=300,
        )
        success = proc.returncode == 0
    except FileNotFoundError:
        success = False
    except subprocess.TimeoutExpired:
        success = False

    env_configured = False
    env_backup_name = None
    migrate_success = False
    if success:
        env_values = _configure_env(stdscr, answers)
        if env_values is not None:
            env_path = BASE_DIR / ".env"
            backup_env = backup_file(env_path)
            env_backup_name = backup_env.name if backup_env else None
            env_content = generate_env_content(answers, env_values)
            env_path.write_text(env_content, encoding="utf-8")
            env_configured = True

            _page_progress(stdscr, 3, 3, "正在执行数据库迁移 ...")
            try:
                migrate_proc = subprocess.run(
                    ["uv", "run", "python", "manage.py", "migrate"],
                    cwd=BASE_DIR,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                migrate_success = migrate_proc.returncode == 0
            except FileNotFoundError:
                migrate_success = False
            except subprocess.TimeoutExpired:
                migrate_success = False

    _page_result(stdscr, success, answers, backup_name, env_configured, env_backup_name, migrate_success)


def _generate_secret(length=50):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _load_existing_env(env_path):
    values = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                values[key.strip()] = val.strip()
    return values


def _get_env_items(answers):
    db = answers.get("db", "sqlite")
    db_port_default = {"mysql": "3306", "postgresql": "5432"}.get(db, "3306")
    db_user_default = {"mysql": "root", "postgresql": "postgres"}.get(db, "root")

    items = []

    items.append(("group", "核心配置"))
    items.append(("field", {"key": "DEBUG", "default": "True", "desc": "调试模式（生产环境必须 False）", "type": "bool"}))
    items.append(("field", {"key": "DJANGO_SECRET_KEY", "default": "", "desc": "Django 密钥", "type": "secret"}))
    items.append(("field", {"key": "ALLOWED_HOSTS", "default": "localhost,127.0.0.1", "desc": "允许访问的主机", "type": "list"}))
    items.append(("field", {"key": "CSRF_TRUSTED_ORIGINS", "default": "https://localhost,https://127.0.0.1", "desc": "CSRF 可信来源", "type": "list"}))

    items.append(("group", "数据库配置"))
    items.append(("field", {"key": "DB_ENGINE", "default": db, "desc": "数据库引擎（根据之前的选择自动设置）", "type": "auto"}))
    if db != "sqlite":
        items.append(("field", {"key": "DB_HOST", "default": "127.0.0.1", "desc": "数据库主机", "type": "text"}))
        items.append(("field", {"key": "DB_PORT", "default": db_port_default, "desc": "数据库端口", "type": "text"}))
        items.append(("field", {"key": "DB_NAME", "default": "zasca", "desc": "数据库名称", "type": "text"}))
        items.append(("field", {"key": "DB_USER", "default": db_user_default, "desc": "数据库用户", "type": "text"}))
        items.append(("field", {"key": "DB_PASSWORD", "default": "", "desc": "数据库密码", "type": "secret"}))

    if answers.get("redis"):
        items.append(("group", "Redis 配置"))
        items.append(("field", {"key": "REDIS_URL", "default": "redis://localhost:6379/0", "desc": "Redis 连接地址", "type": "text"}))

    if answers.get("celery"):
        items.append(("group", "Celery 配置"))
        items.append(("field", {"key": "CELERY_BROKER_URL", "default": "", "desc": "Celery Broker（留空自动选择）", "type": "text"}))
        items.append(("field", {"key": "CELERY_RESULT_BACKEND", "default": "", "desc": "Celery 结果后端（留空自动选择）", "type": "text"}))

    items.append(("group", "演示模式"))
    items.append(("field", {"key": "ZASCA_DEMO", "default": "0", "desc": "演示模式（1=启用）", "type": "text"}))

    items.append(("group", "安全配置"))
    items.append(("field", {"key": "SECURE_SSL_REDIRECT", "default": "False", "desc": "SSL 重定向", "type": "bool"}))
    items.append(("field", {"key": "SESSION_COOKIE_SECURE", "default": "False", "desc": "会话 Cookie 安全", "type": "bool"}))
    items.append(("field", {"key": "CSRF_COOKIE_SECURE", "default": "False", "desc": "CSRF Cookie 安全", "type": "bool"}))

    items.append(("group", "日志配置"))
    items.append(("field", {"key": "LOG_LEVEL", "default": "DEBUG", "desc": "日志级别", "type": "text"}))
    items.append(("field", {"key": "LOG_FILE", "default": "/var/log/2c2a/application.log", "desc": "日志文件路径", "type": "text"}))

    if answers.get("winrm"):
        items.append(("group", "WinRM 配置"))
        items.append(("field", {"key": "WINRM_TIMEOUT", "default": "30", "desc": "WinRM 超时(秒)", "type": "text"}))
        items.append(("field", {"key": "WINRM_RETRY_COUNT", "default": "3", "desc": "WinRM 重试次数", "type": "text"}))

    items.append(("group", "Gateway 配置"))
    items.append(("field", {"key": "GATEWAY_ENABLED", "default": "False", "desc": "Gateway 开关", "type": "bool"}))
    items.append(("field", {"key": "GATEWAY_CONTROL_SOCKET", "default": "/run/zasca/control.sock", "desc": "Gateway 控制套接字", "type": "text"}))

    items.append(("group", "Beta 数据库配置（可选）"))
    items.append(("field", {"key": "BETA_DB_NAME", "default": "", "desc": "Beta 数据库名称（留空跳过）", "type": "text"}))
    items.append(("field", {"key": "BETA_DB_USER", "default": "", "desc": "Beta 数据库用户", "type": "text"}))
    items.append(("field", {"key": "BETA_DB_PASSWORD", "default": "", "desc": "Beta 数据库密码", "type": "secret"}))
    items.append(("field", {"key": "BETA_DB_HOST", "default": "", "desc": "Beta 数据库主机", "type": "text"}))
    items.append(("field", {"key": "BETA_DB_PORT", "default": "", "desc": "Beta 数据库端口", "type": "text"}))

    items.append(("group", "Bootstrap 认证配置"))
    items.append(("field", {"key": "BOOTSTRAP_SHARED_SALT", "default": "", "desc": "Bootstrap 共享盐值", "type": "secret"}))

    return items


def _step_bool(stdscr, field_data, current_val, step, total):
    key = field_data["key"]
    desc = field_data.get("desc", "")
    selected = 0 if current_val == "True" else 1

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(72, max_x - 4)
        box_h = 10
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = f" 环境变量配置 ({step}/{total}) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        ry = box_y + 2
        _safe_addstr(stdscr, ry, box_x + 4, key, curses.color_pair(C_SELECTED) | curses.A_BOLD)

        ry += 1
        if desc:
            _safe_addstr(stdscr, ry, box_x + 4, desc[:box_w - 8], curses.color_pair(C_DESC))

        ry += 2
        options = [("True", "启用"), ("False", "禁用")]
        for i, (val, label) in enumerate(options):
            is_sel = (i == selected)
            marker = "◉" if is_sel else "○"
            m_color = C_RADIO_ON | curses.A_BOLD if is_sel else C_RADIO_OFF
            ox = box_x + 6 + i * 22
            _safe_addstr(stdscr, ry, ox, marker, curses.color_pair(m_color))
            _safe_addstr(stdscr, ry, ox + 2, f" {label} ({val})", curses.color_pair(C_SELECTED if is_sel else C_UNSELECTED) | curses.A_BOLD)

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "←→/Space 切换  Enter 确认  Esc 返回")

        stdscr.refresh()

        ch = stdscr.getch()
        if ch == curses.KEY_LEFT:
            selected = 0
        elif ch == curses.KEY_RIGHT:
            selected = 1
        elif ch == ord(' '):
            selected = 1 - selected
        elif ch in (curses.KEY_ENTER, 10, 13):
            return "True" if selected == 0 else "False"
        elif ch == 27:
            return None


def _step_secret(stdscr, field_data, current_val, is_auto, step, total):
    key = field_data["key"]
    desc = field_data.get("desc", "")

    if is_auto or not current_val:
        radio = 0
    else:
        radio = 1

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(72, max_x - 4)
        box_h = 12
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = f" 环境变量配置 ({step}/{total}) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        ry = box_y + 2
        _safe_addstr(stdscr, ry, box_x + 4, key, curses.color_pair(C_SELECTED) | curses.A_BOLD)

        ry += 1
        if desc:
            _safe_addstr(stdscr, ry, box_x + 4, desc[:box_w - 8], curses.color_pair(C_DESC))

        ry += 2
        is_sel0 = (radio == 0)
        marker0 = "◉" if is_sel0 else "○"
        m_color0 = C_RADIO_ON | curses.A_BOLD if is_sel0 else C_RADIO_OFF
        _safe_addstr(stdscr, ry, box_x + 4, marker0, curses.color_pair(m_color0))
        _safe_addstr(stdscr, ry, box_x + 7, "随机生成（推荐）", curses.color_pair(C_SELECTED if is_sel0 else C_UNSELECTED) | curses.A_BOLD)

        ry += 1
        sub_desc = "自动生成包含字母、数字和符号的50位密钥"
        _safe_addstr(stdscr, ry, box_x + 7, sub_desc[:box_w - 10], curses.color_pair(C_DESC))

        if is_sel0 and is_auto and current_val:
            ry += 1
            preview = current_val[:8] + "..." + current_val[-4:] if len(current_val) > 12 else current_val
            _safe_addstr(stdscr, ry, box_x + 7, f"预览: {preview}", curses.color_pair(C_DESC))

        ry += 2
        is_sel1 = (radio == 1)
        marker1 = "◉" if is_sel1 else "○"
        m_color1 = C_RADIO_ON | curses.A_BOLD if is_sel1 else C_RADIO_OFF
        _safe_addstr(stdscr, ry, box_x + 4, marker1, curses.color_pair(m_color1))
        _safe_addstr(stdscr, ry, box_x + 7, "手动输入", curses.color_pair(C_SELECTED if is_sel1 else C_UNSELECTED) | curses.A_BOLD)

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "↑↓ 选择  Enter 确认  Esc 返回")

        stdscr.refresh()

        ch = stdscr.getch()
        if ch == curses.KEY_UP:
            radio = 0
        elif ch == curses.KEY_DOWN:
            radio = 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            if radio == 0:
                if not current_val or not is_auto:
                    current_val = _generate_secret(50)
                return current_val, True
            else:
                result = _step_text(stdscr, field_data, current_val, step, total)
                if result is not None:
                    return result, False
                continue
        elif ch == 27:
            return None, None


def _step_text(stdscr, field_data, current_val, step, total):
    key = field_data["key"]
    desc = field_data.get("desc", "")
    curses.curs_set(1)
    buf = list(current_val)
    pos = len(buf)

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(72, max_x - 4)
        box_h = 10
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = f" 环境变量配置 ({step}/{total}) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        ry = box_y + 2
        _safe_addstr(stdscr, ry, box_x + 4, key, curses.color_pair(C_SELECTED) | curses.A_BOLD)

        ry += 1
        if desc:
            _safe_addstr(stdscr, ry, box_x + 4, desc[:box_w - 8], curses.color_pair(C_DESC))

        ry += 2
        input_x = box_x + 4
        input_w = box_w - 8
        _safe_addstr(stdscr, ry, input_x, " " * input_w, curses.color_pair(C_HIGHLIGHT))

        text = "".join(buf)
        if len(text) > input_w:
            start = max(0, pos - input_w + 1)
            visible_text = text[start:start + input_w]
            cursor_offset = pos - start
        else:
            visible_text = text
            cursor_offset = pos

        _safe_addstr(stdscr, ry, input_x, visible_text[:input_w], curses.color_pair(C_HIGHLIGHT))

        try:
            stdscr.move(ry, input_x + min(cursor_offset, input_w - 1))
        except curses.error:
            pass

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "Enter 确认  Esc 返回  Ctrl+U 清空")

        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            curses.curs_set(0)
            return "".join(buf)
        elif ch == 27:
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if pos > 0:
                buf.pop(pos - 1)
                pos -= 1
        elif ch == curses.KEY_DC:
            if pos < len(buf):
                buf.pop(pos)
        elif ch == curses.KEY_LEFT:
            if pos > 0:
                pos -= 1
        elif ch == curses.KEY_RIGHT:
            if pos < len(buf):
                pos += 1
        elif ch == curses.KEY_HOME:
            pos = 0
        elif ch == curses.KEY_END:
            pos = len(buf)
        elif ch == 21:
            buf.clear()
            pos = 0
        elif 32 <= ch < 127:
            buf.insert(pos, chr(ch))
            pos += 1


def _step_auto(stdscr, field_data, current_val, step, total):
    key = field_data["key"]
    desc = field_data.get("desc", "")

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(72, max_x - 4)
        box_h = 10
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 2

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = f" 环境变量配置 ({step}/{total}) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        ry = box_y + 2
        _safe_addstr(stdscr, ry, box_x + 4, key, curses.color_pair(C_SELECTED) | curses.A_BOLD)

        ry += 1
        if desc:
            _safe_addstr(stdscr, ry, box_x + 4, desc[:box_w - 8], curses.color_pair(C_DESC))

        ry += 2
        _safe_addstr(stdscr, ry, box_x + 4, f"▸ {current_val}", curses.color_pair(C_SUCCESS) | curses.A_BOLD)

        ry += 1
        _safe_addstr(stdscr, ry, box_x + 4, "（此值由之前的选择自动确定）", curses.color_pair(C_DESC))

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "Enter 继续  Esc 返回")

        stdscr.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_ENTER, 10, 13):
            return current_val
        elif ch == 27:
            return None


def _step_list(stdscr, field_data, current_val, step, total):
    key = field_data["key"]
    desc = field_data.get("desc", "")
    items = [x.strip() for x in current_val.split(",") if x.strip()] if current_val else []
    cursor = 0
    scroll = 0

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(72, max_x - 4)
        box_h = max(14, min(20, max_y - 4))
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 1

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = f" 环境变量配置 ({step}/{total}) "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        ry = box_y + 2
        _safe_addstr(stdscr, ry, box_x + 4, key, curses.color_pair(C_SELECTED) | curses.A_BOLD)

        ry += 1
        if desc:
            _safe_addstr(stdscr, ry, box_x + 4, desc[:box_w - 8], curses.color_pair(C_DESC))

        ry += 2
        max_list_visible = box_h - 8
        max_scroll = max(0, len(items) - max_list_visible)
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + max_list_visible:
            scroll = cursor - max_list_visible + 1
        scroll = max(0, min(scroll, max_scroll))

        if not items:
            _safe_addstr(stdscr, ry, box_x + 6, "（空列表，按 + 添加项）", curses.color_pair(C_DESC))
        else:
            visible_items = items[scroll:scroll + max_list_visible]
            for i, item in enumerate(visible_items):
                actual_idx = scroll + i
                iy = ry + i
                is_active = (actual_idx == cursor)
                marker = "▸" if is_active else " "
                line = f"  {marker} {item}"
                if is_active:
                    _safe_addstr(stdscr, iy, box_x + 4, line[:box_w - 8], curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD)
                else:
                    _safe_addstr(stdscr, iy, box_x + 4, line[:box_w - 8], curses.color_pair(C_UNSELECTED))

        count_y = box_y + box_h - 3
        _safe_addstr(stdscr, count_y, box_x + 4, f"共 {len(items)} 项", curses.color_pair(C_DESC))

        if max_scroll > 0:
            scroll_info = f" [{scroll + 1}-{min(scroll + max_list_visible, len(items))}/{len(items)}] "
            _safe_addstr(stdscr, count_y, box_x + box_w - len(scroll_info) - 2, scroll_info, curses.color_pair(C_DESC))

        hint_y = box_y + box_h + 1
        _draw_hint(stdscr, hint_y, box_x + 2, "↑↓ 切换  + 添加  - 删除  Enter 编辑  Ctrl+D 完成  Esc 返回")

        stdscr.refresh()

        ch = stdscr.getch()
        if ch == curses.KEY_UP:
            if items:
                cursor = max(0, cursor - 1)
        elif ch == curses.KEY_DOWN:
            if items:
                cursor = min(len(items) - 1, cursor + 1)
        elif ch in (ord('+'), ord('=')):
            new_item = _step_text(stdscr, {"key": f"{key}[新项]", "desc": "输入新项的值"}, "", step, total)
            if new_item is not None and new_item.strip():
                items.append(new_item.strip())
                cursor = len(items) - 1
        elif ch in (ord('-'), ord('_')):
            if items and 0 <= cursor < len(items):
                items.pop(cursor)
                if cursor >= len(items) and len(items) > 0:
                    cursor = len(items) - 1
        elif ch in (curses.KEY_ENTER, 10, 13):
            if items and 0 <= cursor < len(items):
                new_item = _step_text(stdscr, {"key": f"{key}[{cursor}]", "desc": "编辑当前项"}, items[cursor], step, total)
                if new_item is not None:
                    items[cursor] = new_item.strip() if new_item.strip() else items[cursor]
        elif ch == 4:
            return ",".join(items)
        elif ch == 27:
            return None


def _env_preview(stdscr, items, values, secret_auto):
    field_indices = [i for i, (kind, _) in enumerate(items) if kind == "field"]
    cursor = 0
    scroll = 0

    while True:
        _init_colors()
        stdscr.clear()
        max_y, max_x = stdscr.getmaxyx()

        box_w = min(76, max_x - 4)
        box_h = max_y - 5
        box_x = max(0, (max_x - box_w) // 2)
        box_y = 1

        _draw_banner(stdscr, 0, max_x)
        _draw_box(stdscr, box_y, box_x, box_h, box_w)

        title = " .env 配置预览 "
        tx = box_x + max(0, (box_w - len(title)) // 2)
        _safe_addstr(stdscr, box_y, tx, title, curses.color_pair(C_TITLE) | curses.A_BOLD)

        cursor_item_idx = field_indices[cursor] if cursor < len(field_indices) else 0

        max_visible = box_h - 3
        total_items = len(items)
        max_scroll = max(0, total_items - max_visible)

        if cursor_item_idx < scroll:
            scroll = cursor_item_idx
        elif cursor_item_idx >= scroll + max_visible:
            scroll = cursor_item_idx - max_visible + 1
        scroll = max(0, min(scroll, max_scroll))

        visible = items[scroll:scroll + max_visible]
        current_visible_idx = cursor_item_idx - scroll

        for i, (kind, data) in enumerate(visible):
            ry = box_y + 1 + i
            rx = box_x + 2
            remaining = box_w - 5

            if kind == "group":
                _safe_addstr(stdscr, ry, rx, f"  {data}", curses.color_pair(C_SUBTITLE) | curses.A_BOLD)
            elif kind == "field":
                is_active = (i == current_visible_idx)
                key = data["key"]
                val = values.get(key, data["default"])
                ftype = data.get("type", "text")

                if ftype == "secret":
                    if key in secret_auto:
                        if val:
                            preview = val[:6] + "..." + val[-4:] if len(val) > 10 else val
                            display = f"(随机: {preview})"
                        else:
                            display = "(随机生成)"
                    elif val:
                        display = "******"
                    else:
                        display = "(未设置)"
                elif ftype == "auto":
                    display = f"{val}  (自动)"
                elif ftype == "bool":
                    display = val
                elif ftype == "list":
                    list_items = [x.strip() for x in val.split(",") if x.strip()] if val else []
                    if list_items:
                        display = ", ".join(list_items)
                    else:
                        display = "(空列表)"
                else:
                    display = val if val else "(空)"

                line = f"  {key} = {display}"

                if is_active:
                    _safe_addstr(stdscr, ry, rx, line[:remaining], curses.color_pair(C_HIGHLIGHT) | curses.A_BOLD)
                else:
                    color = C_DESC if ftype == "auto" else C_UNSELECTED
                    _safe_addstr(stdscr, ry, rx, line[:remaining], curses.color_pair(color))

        desc_y = box_y + box_h - 2
        if 0 <= current_visible_idx < len(visible) and visible[current_visible_idx][0] == "field":
            field_data = visible[current_visible_idx][1]
            desc = field_data.get("desc", "")
            if desc:
                _safe_addstr(stdscr, desc_y, box_x + 3, f"  {desc}"[:box_w - 6], curses.color_pair(C_DESC))

        if max_scroll > 0:
            scroll_info = f" [{scroll + 1}-{min(scroll + max_visible, total_items)}/{total_items}] "
            _safe_addstr(stdscr, desc_y, box_x + box_w - len(scroll_info) - 2, scroll_info, curses.color_pair(C_DESC))

        hint_y = box_y + box_h + 1
        hint = "↑↓ 移动  Enter 编辑  S 保存  Esc 取消"
        if max_scroll > 0:
            hint = "↑↓/PgUp/PgDn 滚动  " + hint
        _draw_hint(stdscr, hint_y, box_x + 2, hint)

        stdscr.refresh()

        ch = stdscr.getch()
        if ch == curses.KEY_UP:
            cursor = max(0, cursor - 1)
        elif ch == curses.KEY_DOWN:
            cursor = min(len(field_indices) - 1, cursor + 1)
        elif ch == curses.KEY_PPAGE:
            cursor = max(0, cursor - 5)
        elif ch == curses.KEY_NPAGE:
            cursor = min(len(field_indices) - 1, cursor + 5)
        elif ch in (curses.KEY_ENTER, 10, 13):
            field_data = items[field_indices[cursor]][1]
            ftype = field_data.get("type", "text")
            key = field_data["key"]
            current = values.get(key, field_data["default"])

            if ftype == "bool":
                result = _step_bool(stdscr, field_data, current, cursor + 1, len(field_indices))
                if result is not None:
                    values[key] = result
            elif ftype == "secret":
                is_auto_flag = key in secret_auto
                result, auto = _step_secret(stdscr, field_data, current, is_auto_flag, cursor + 1, len(field_indices))
                if result is not None:
                    values[key] = result
                    if auto:
                        secret_auto.add(key)
                    else:
                        secret_auto.discard(key)
            elif ftype == "list":
                result = _step_list(stdscr, field_data, current, cursor + 1, len(field_indices))
                if result is not None:
                    values[key] = result
            else:
                result = _step_text(stdscr, field_data, current, cursor + 1, len(field_indices))
                if result is not None:
                    values[key] = result
        elif ch in (ord('s'), ord('S')):
            return values
        elif ch == 27:
            return None


def _configure_env(stdscr, answers):
    items = _get_env_items(answers)
    field_items = [(i, data) for i, (kind, data) in enumerate(items) if kind == "field"]
    total = len(field_items)

    existing = _load_existing_env(BASE_DIR / ".env")
    values = {}
    secret_auto = set()

    for idx, data in field_items:
        key = data["key"]
        if data.get("type") == "auto":
            values[key] = data["default"]
        elif key in existing:
            values[key] = existing[key]
        else:
            values[key] = data["default"]

    step = 0
    while 0 <= step < total:
        idx, data = field_items[step]
        ftype = data.get("type", "text")
        key = data["key"]
        current = values.get(key, data["default"])

        if ftype == "bool":
            result = _step_bool(stdscr, data, current, step + 1, total)
            if result is None:
                step -= 1
                continue
            values[key] = result
            step += 1
        elif ftype == "secret":
            is_auto_flag = key in secret_auto
            result, auto = _step_secret(stdscr, data, current, is_auto_flag, step + 1, total)
            if result is None:
                step -= 1
                continue
            values[key] = result
            if auto:
                secret_auto.add(key)
            else:
                secret_auto.discard(key)
            step += 1
        elif ftype == "auto":
            result = _step_auto(stdscr, data, current, step + 1, total)
            if result is None:
                step -= 1
                continue
            step += 1
        elif ftype == "list":
            result = _step_list(stdscr, data, current, step + 1, total)
            if result is None:
                step -= 1
                continue
            values[key] = result
            step += 1
        else:
            result = _step_text(stdscr, data, current, step + 1, total)
            if result is None:
                step -= 1
                continue
            values[key] = result
            step += 1

    if step < 0:
        return None

    result = _env_preview(stdscr, items, values, secret_auto)
    if result is None:
        return None

    return result


def generate_env_content(answers, values):
    lines = []
    lines.append("# ZASCA 环境配置文件")
    lines.append("# 由 deploy.py 自动生成")
    lines.append("")

    lines.append("# ========== 核心配置 ==========")
    lines.append(f"DEBUG={values.get('DEBUG', 'True')}")

    secret_key = values.get('DJANGO_SECRET_KEY', '')
    if not secret_key:
        secret_key = _generate_secret(50)
    lines.append(f"DJANGO_SECRET_KEY={secret_key}")

    lines.append(f"ALLOWED_HOSTS={values.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')}")
    lines.append(f"CSRF_TRUSTED_ORIGINS={values.get('CSRF_TRUSTED_ORIGINS', 'https://localhost,https://127.0.0.1')}")
    lines.append("")

    db = answers.get("db", "sqlite")
    lines.append("# ========== 数据库配置 ==========")
    lines.append(f"DB_ENGINE={values.get('DB_ENGINE', db)}")
    if db != "sqlite":
        lines.append(f"DB_HOST={values.get('DB_HOST', '127.0.0.1')}")
        lines.append(f"DB_PORT={values.get('DB_PORT', '3306')}")
        lines.append(f"DB_NAME={values.get('DB_NAME', 'zasca')}")
        lines.append(f"DB_USER={values.get('DB_USER', 'root')}")
        db_pass = values.get('DB_PASSWORD', '')
        if not db_pass:
            db_pass = _generate_secret(50)
        lines.append(f"DB_PASSWORD={db_pass}")
    lines.append("")

    if answers.get("redis"):
        lines.append("# ========== Redis 配置 ==========")
        lines.append(f"REDIS_URL={values.get('REDIS_URL', 'redis://localhost:6379/0')}")
        lines.append("")

    if answers.get("celery"):
        lines.append("# ========== Celery 配置 ==========")
        broker = values.get('CELERY_BROKER_URL', '')
        backend = values.get('CELERY_RESULT_BACKEND', '')
        if not broker and answers.get("redis"):
            redis_url = values.get('REDIS_URL', 'redis://localhost:6379/0')
            broker = redis_url.replace('/0', '/1')
        if not backend and answers.get("redis"):
            redis_url = values.get('REDIS_URL', 'redis://localhost:6379/0')
            backend = redis_url.replace('/0', '/2')
        if broker:
            lines.append(f"CELERY_BROKER_URL={broker}")
        if backend:
            lines.append(f"CELERY_RESULT_BACKEND={backend}")
        lines.append("")

    lines.append("# ========== 演示模式 ==========")
    lines.append(f"ZASCA_DEMO={values.get('ZASCA_DEMO', '0')}")
    lines.append("")

    lines.append("# ========== 安全配置 ==========")
    lines.append(f"SECURE_SSL_REDIRECT={values.get('SECURE_SSL_REDIRECT', 'False')}")
    lines.append(f"SESSION_COOKIE_SECURE={values.get('SESSION_COOKIE_SECURE', 'False')}")
    lines.append(f"CSRF_COOKIE_SECURE={values.get('CSRF_COOKIE_SECURE', 'False')}")
    lines.append("")

    lines.append("# ========== 日志配置 ==========")
    lines.append(f"LOG_LEVEL={values.get('LOG_LEVEL', 'DEBUG')}")
    lines.append(f"LOG_FILE={values.get('LOG_FILE', '/var/log/2c2a/application.log')}")
    lines.append("")

    if answers.get("winrm"):
        lines.append("# ========== WinRM 配置 ==========")
        lines.append(f"WINRM_TIMEOUT={values.get('WINRM_TIMEOUT', '30')}")
        lines.append(f"WINRM_RETRY_COUNT={values.get('WINRM_RETRY_COUNT', '3')}")
        lines.append("")

    lines.append("# ========== Gateway 配置 ==========")
    lines.append(f"GATEWAY_ENABLED={values.get('GATEWAY_ENABLED', 'False')}")
    lines.append(f"GATEWAY_CONTROL_SOCKET={values.get('GATEWAY_CONTROL_SOCKET', '/run/zasca/control.sock')}")
    lines.append("")

    beta_fields = ['BETA_DB_NAME', 'BETA_DB_USER', 'BETA_DB_PASSWORD', 'BETA_DB_HOST', 'BETA_DB_PORT']
    has_beta = any(values.get(f, '') for f in beta_fields)
    if has_beta:
        lines.append("# ========== Beta 数据库配置 ==========")
        for f in beta_fields:
            if f == 'BETA_DB_PASSWORD':
                bp = values.get(f, '')
                if not bp:
                    bp = _generate_secret(50)
                lines.append(f"{f}={bp}")
            else:
                lines.append(f"{f}={values.get(f, '')}")
        lines.append("")

    lines.append("# ========== Bootstrap 认证配置 ==========")
    salt = values.get('BOOTSTRAP_SHARED_SALT', '')
    if not salt:
        salt = _generate_secret(50)
    lines.append(f"BOOTSTRAP_SHARED_SALT={salt}")
    lines.append("")

    return "\n".join(lines)


def compute_dependencies(answers):
    deps = dict(DEPS_CORE)

    if answers.get("celery"):
        deps.update(DEPS_CELERY)

    if answers["db"] == "mysql":
        deps.update(DEPS_MYSQL)
    elif answers["db"] == "postgresql":
        deps.update(DEPS_POSTGRESQL)

    if answers.get("redis"):
        deps.update(DEPS_REDIS)

    if answers.get("celery") and not answers.get("redis"):
        deps.update(DEPS_SQLITE_BROKER)

    if answers.get("winrm"):
        deps.update(DEPS_WINRM)

    if answers.get("kerberos"):
        deps.update(DEPS_KERBEROS)

    if answers.get("markdown"):
        deps.update(DEPS_MARKDOWN)

    if answers.get("2fa"):
        deps.update(DEPS_2FA)

    dev_deps = dict(DEPS_DEV) if answers.get("dev") else {}

    return deps, dev_deps


def generate_pyproject_toml(answers, deps, dev_deps):
    lines = []

    lines.append("[project]")
    lines.append('name = "2c2a"')
    lines.append('version = "1.0.0"')
    lines.append('description = "2c2a - Django Web Application"')
    lines.append('license = "AGPL-3.0-only"')
    lines.append('readme = "README.md"')
    lines.append('requires-python = ">=3.10"')

    sorted_deps = sorted(deps.values(), key=_dep_sort_key)
    lines.append("dependencies = [")
    for spec in sorted_deps:
        lines.append(f'    "{spec}",')
    lines.append("]")

    optional_groups = {}
    if not answers.get("redis"):
        optional_groups["redis"] = sorted(DEPS_REDIS.values())
    if not answers.get("kerberos"):
        optional_groups["kerberos"] = sorted(DEPS_KERBEROS.values())
    if not answers.get("winrm"):
        optional_groups["winrm"] = sorted(DEPS_WINRM.values())

    if optional_groups:
        lines.append("")
        lines.append("[project.optional-dependencies]")
        for group_name, group_deps in optional_groups.items():
            lines.append(f"{group_name} = [")
            for spec in group_deps:
                lines.append(f'    "{spec}",')
            lines.append("]")

    lines.append("")
    lines.append("[build-system]")
    lines.append('requires = ["hatchling"]')
    lines.append('build-backend = "hatchling.build"')

    if dev_deps:
        lines.append("")
        lines.append("[dependency-groups]")
        lines.append("dev = [")
        for spec in sorted(dev_deps.values()):
            lines.append(f'    "{spec}",')
        lines.append("]")

    lines.append("")
    lines.append("[tool.hatch.metadata]")
    lines.append("allow-direct-references = true")

    lines.append("")
    lines.append("[tool.hatch.build.targets.wheel]")
    lines.append('packages = ["."]')

    lines.append("")
    lines.append("[tool.pyright]")
    lines.append('venvPath = "."')
    lines.append('venv = ".venv"')
    lines.append('pythonVersion = "3.13"')
    lines.append('typeCheckingMode = "basic"')

    lines.append("")
    lines.append("[tool.pyrefly]")
    lines.append('python-version = "3.13"')

    lines.append("")
    return "\n".join(lines)


def _dep_sort_key(spec):
    if "@" in spec:
        return (1, spec.lower())
    return (0, spec.lower())


def backup_file(path):
    if not path.exists():
        return None
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}.bak.{ts}{path.suffix}")
    shutil.copy2(path, backup)
    return backup


def main():
    if not sys.stdin.isatty():
        print("错误: 此脚本需要交互式终端")
        sys.exit(1)

    try:
        curses.wrapper(_tui_main)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
