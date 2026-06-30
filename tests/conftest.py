"""共享测试 fixtures。

在导入任何 app 模块之前设置测试环境变量，确保：
- 使用 SQLite 文件数据库（无需 PostgreSQL）
- 禁用 Redis（无需真实 Redis 服务）
- DEMO 模式自动派生密钥（无需显式配置 Ed25519/AES/BLAKE2b 密钥）

关键：测试引擎必须在事件循环内创建（session 级 async fixture），
不能在模块导入时创建。aiosqlite 的连接与创建时的事件循环绑定，
导入时创建的引擎在 pytest-asyncio 的事件循环中无法正确提交 DDL。
"""
import os
import tempfile

# ── 必须在导入 app 模块之前设置环境变量 ──
os.environ["2C2A_DEMO"] = "1"
os.environ["DEBUG"] = "1"
os.environ["DB_ENGINE"] = "sqlite"
os.environ["REDIS_ENABLED"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key-for-tests-only-not-production"

import hashlib
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 导入 app 模块（环境变量已设置）
import app.core.db as db_module
import app.tenant.middleware as middleware_module
from app.api.v1.hosts import router as hosts_router
from app.api.v1.tickets import router as tickets_router
from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.routes import router as auth_router
from app.core.exceptions import register_exception_handlers
from app.models import Base
from app.models.host import Host
from app.models.tenant import SiteGroup, SiteGroupHostname, SystemConfig
from app.models.ticket import Ticket, TicketCategory
from app.models.user import User, UserProfile
from app.security.password import hash_password
from app.tenant.middleware import TenantMiddleware
from app.tenant.resolver import TenantContext

# 模块级占位（实际引擎在 session fixture 中创建并替换）
test_engine = None
TestSessionLocal = None


def blake2b_prehash(password: str) -> str:
    """模拟前端 BLAKE2b 预哈希（digest_size=64，输出 128 字符 hex）。"""
    return hashlib.blake2b(password.encode(), digest_size=64).hexdigest()


def create_test_app() -> FastAPI:
    """创建最小化测试 FastAPI 应用（不含插件加载 lifespan）。"""
    app = FastAPI(title="test")
    app.add_middleware(TenantMiddleware)
    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(hosts_router, prefix="/api/v1")
    app.include_router(tickets_router, prefix="/api/v1")
    return app


def _make_auth_override(
    is_staff: bool = False,
    is_superuser: bool = False,
    user_id: int = 1,
    username: str = "testuser",
    site_group_id: int | None = None,
):
    """构造 get_current_user 依赖覆盖函数。"""

    async def override():
        return CurrentUser(
            id=user_id,
            username=username,
            is_superuser=is_superuser,
            is_staff=is_staff,
            ban_version=0,
            site_group_id=site_group_id,
            db_user=None,
        )

    return override


# ──────────────────────────────────────────────
# Session 级引擎 fixture（必须在事件循环内创建）
# ──────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def _init_engine():
    """在 session 事件循环内创建测试引擎并替换模块级引用。

    aiosqlite 连接绑定到创建时的事件循环。若引擎在模块导入时
    （无事件循环）创建，后续 begin()/connect() 无法正确提交 DDL。
    """
    global test_engine, TestSessionLocal

    _test_db_fd, test_db_path = tempfile.mkstemp(suffix=".db")
    os.close(_test_db_fd)
    test_db_url = f"sqlite+aiosqlite:///{test_db_path.replace(os.sep, '/')}"

    engine = create_async_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
    )
    session_local = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # 替换模块级引用，使 get_db 与 TenantMiddleware 使用测试库
    test_engine = engine
    TestSessionLocal = session_local
    db_module.engine = engine
    db_module.AsyncSessionLocal = session_local
    middleware_module.AsyncSessionLocal = session_local

    yield engine, session_local

    await engine.dispose()
    try:
        os.unlink(test_db_path)
    except OSError:
        pass


# ──────────────────────────────────────────────
# 数据库 fixtures
# ──────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def _setup_db(_init_engine):
    """每个测试前后创建/销毁全部表，保证隔离。"""
    engine, _ = _init_engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(_init_engine) -> AsyncIterator[AsyncSession]:
    """异步数据库会话，用于直接操作 DB。"""
    _, session_local = _init_engine
    async with session_local() as session:
        yield session


# ──────────────────────────────────────────────
# FastAPI / HTTP client fixtures
# ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_instance():
    """测试 FastAPI 应用实例。"""
    return create_test_app()


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncIterator[AsyncClient]:
    """HTTP 测试客户端（无认证覆盖，走真实认证流程）。"""
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def staff_client(app_instance) -> AsyncIterator[AsyncClient]:
    """HTTP 客户端（staff 用户认证覆盖）。"""
    app_instance.dependency_overrides[get_current_user] = _make_auth_override(
        is_staff=True, is_superuser=False, user_id=1
    )
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def superuser_client(app_instance) -> AsyncIterator[AsyncClient]:
    """HTTP 客户端（超级管理员认证覆盖）。"""
    app_instance.dependency_overrides[get_current_user] = _make_auth_override(
        is_staff=True, is_superuser=True, user_id=1
    )
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://testserver",
    ) as c:
        yield c


@pytest_asyncio.fixture
async def user_client(app_instance) -> AsyncIterator[AsyncClient]:
    """HTTP 客户端（普通用户认证覆盖）。"""
    app_instance.dependency_overrides[get_current_user] = _make_auth_override(
        is_staff=False, is_superuser=False, user_id=1
    )
    async with AsyncClient(
        transport=ASGITransport(app=app_instance),
        base_url="http://testserver",
    ) as c:
        yield c


# ──────────────────────────────────────────────
# 数据 fixtures
# ──────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_user(db_session) -> User:
    """在 DB 中创建测试用户（staff 身份）。"""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash=hash_password(blake2b_prehash("Testpass123!")),
        is_active=True,
        is_staff=True,
        ban_version=0,
    )
    db_session.add(user)
    await db_session.flush()
    db_session.add(UserProfile(user_id=user.id))
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_tenant(db_session) -> SiteGroup:
    """创建测试站点组与主机名绑定。"""
    sg = SiteGroup(
        name="Test Site",
        slug="test-site",
        site_name="Test",
        is_active=True,
    )
    db_session.add(sg)
    await db_session.flush()
    db_session.add(
        SiteGroupHostname(hostname="test.example.com", site_group_id=sg.id)
    )
    await db_session.commit()
    return sg


@pytest_asyncio.fixture
async def test_system_config(db_session) -> SystemConfig:
    """创建系统全局配置（id=1 单例）。"""
    cfg = SystemConfig(
        id=1,
        site_name="2c2a Test",
        enable_registration=False,
    )
    db_session.add(cfg)
    await db_session.commit()
    return cfg
