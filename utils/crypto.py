import base64
import hashlib
from django.conf import settings
from cryptography.fernet import Fernet

_fernet_instance = None

def get_fernet():
    global _fernet_instance
    if _fernet_instance is None:
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        _fernet_instance = Fernet(base64.urlsafe_b64encode(key))
    return _fernet_instance

def encrypt_value(plaintext):
    if not plaintext:
        return ''
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()

def decrypt_value(ciphertext):
    if not ciphertext:
        return ''
    f = get_fernet()
    try:
        return f.decrypt(ciphertext.encode()).decode()
    except Exception:
        raise ValueError("解密失败")
