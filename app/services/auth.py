"""
认证服务

JWT 令牌 + Redis 会话管理
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt
from redis.asyncio import Redis

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AuthService:
    """认证服务（纯静态方法，无状态）"""

    # ========== 密码哈希 ==========

    @staticmethod
    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_password(plain: str, hashed: str) -> bool:
        return bcrypt.checkpw(plain.encode(), hashed.encode())

    # ========== JWT ==========

    @staticmethod
    def create_access_token(user_id: str, extra: dict = None) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
        payload = {"sub": user_id, "exp": expire, "type": "access"}
        if extra:
            payload.update(extra)
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        expire = datetime.now(timezone.utc) + timedelta(
            days=settings.jwt_refresh_token_expire_days
        )
        payload = {"sub": user_id, "exp": expire, "type": "refresh"}
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def verify_token(token: str) -> Optional[dict]:
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.jwt_algorithm]
            )
            return payload
        except JWTError:
            return None

    # ========== Redis 会话 ==========

    @staticmethod
    async def _get_redis() -> Redis:
        from app.services.redis_helper import get_redis
        return await get_redis()

    @staticmethod
    async def create_session(user_id: str, ip_address: str = "", user_agent: str = "") -> str:
        """创建会话，返回 session_id"""
        session_id = uuid4().hex
        redis = await AuthService._get_redis()
        data = json.dumps({
            "user_id": user_id,
            "ip": ip_address,
            "ua": user_agent[:500] if user_agent else "",
        })
        await redis.setex(
            f"session:{session_id}",
            settings.session_expire_seconds,
            data,
        )
        return session_id

    @staticmethod
    async def get_session_user_id(session_id: str) -> Optional[str]:
        """通过 session_id 获取 user_id"""
        redis = await AuthService._get_redis()
        data = await redis.get(f"session:{session_id}")
        if data:
            return json.loads(data).get("user_id")
        return None

    @staticmethod
    async def destroy_session(session_id: str) -> None:
        """销毁会话"""
        redis = await AuthService._get_redis()
        await redis.delete(f"session:{session_id}")

    @staticmethod
    async def refresh_session(session_id: str) -> None:
        """刷新会话过期时间"""
        redis = await AuthService._get_redis()
        await redis.expire(f"session:{session_id}", settings.session_expire_seconds)
