"""
加密服务

基于 Fernet 对称加密，替代 Django 版 crypto.py
使用 settings.encryption_key 或从 settings.secret_key 派生密钥
与旧版 Django crypto.py 保持密钥兼容（相同 secret_key 产生相同 Fernet key）
"""
import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import get_settings

_fernet_instance: Fernet | None = None


def _get_fernet() -> Fernet:
    """获取 Fernet 实例（单例）"""
    global _fernet_instance
    if _fernet_instance is None:
        settings = get_settings()
        if settings.encryption_key:
            # 直接使用配置的 Fernet key
            key = (
                settings.encryption_key.encode()
                if isinstance(settings.encryption_key, str)
                else settings.encryption_key
            )
            _fernet_instance = Fernet(key)
        else:
            # 从 secret_key 派生（与旧版 Django crypto.py 兼容）
            derived = hashlib.sha256(settings.secret_key.encode()).digest()
            _fernet_instance = Fernet(base64.urlsafe_b64encode(derived))
    return _fernet_instance


def encrypt_value(plaintext: str) -> str:
    """加密字符串，返回加密后的字符串"""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_value(ciphertext: str) -> str:
    """解密字符串，返回明文"""
    if not ciphertext:
        return ""
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        raise ValueError("解密失败")
