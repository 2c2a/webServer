"""密码哈希：前端 BLAKE2b 预哈希 + 后端 Argon2id 加盐慢哈希。

流程：
  1. 前端：对原始密码做 BLAKE2b（定长 64 字节 hex），防超长密码 DoS 后端 Argon2id
  2. 后端：校验预哈希格式 → Argon2id 加盐慢哈希 → 存储 PHC 字符串
  3. 验证：前端再次 BLAKE2b → 后端 Argon2id 验证
"""
from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError

from app.core.config import settings
from app.security.crypto import argon2id_hash, argon2id_verify, server_side_prehash

# 与 crypto.argon2id_hash 参数一致的 PasswordHasher 实例（用于 check_needs_rehash）
_ph = PasswordHasher(
    time_cost=settings.argon2_time_cost,
    memory_cost=settings.argon2_memory_cost,
    parallelism=settings.argon2_parallelism,
    type=Type.ID,
)


def hash_password(blake2b_prehash_hex: str) -> str:
    """对前端 BLAKE2b 预哈希做 Argon2id 慢哈希，返回 PHC 字符串。"""
    prehash_bytes = server_side_prehash(blake2b_prehash_hex)
    return argon2id_hash(prehash_bytes)


def verify_password(blake2b_prehash_hex: str, phc_hash: str) -> bool:
    """验证密码：前端 BLAKE2b 预哈希 vs 存储 Argon2id PHC。"""
    try:
        prehash_bytes = server_side_prehash(blake2b_prehash_hex)
    except ValueError:
        return False
    if not phc_hash:
        return False
    return argon2id_verify(prehash_bytes, phc_hash)


def needs_rehash(phc_hash: str) -> bool:
    """检查 Argon2id 参数是否需要重新哈希（参数升级时）。"""
    try:
        return _ph.check_needs_rehash(phc_hash)
    except (InvalidHashError, Exception):
        return True
