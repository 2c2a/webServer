"""共享 API 依赖。"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser, get_current_user
from app.core.db import get_db
from app.tenant.dependencies import get_tenant
from app.tenant.resolver import TenantContext


class DBDep:
    def __init__(self, db: AsyncSession = Depends(get_db)):
        self.db = db


class APIAuth:
    def __init__(self, user: CurrentUser = Depends(get_current_user)):
        self.user = user
