"""
辅助函数模块

提供项目中常用的辅助函数（FastAPI 版本，替代 Django 版 helpers.py）
"""
import json
import re
import secrets
import string
from datetime import datetime
from typing import Any, Optional

from fastapi import Request


def get_client_ip(request: Request) -> Optional[str]:
    """从 FastAPI Request 中提取客户端 IP，支持 X-Forwarded-For"""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def generate_complex_password(length: int = 16) -> str:
    """生成包含大小写字母、数字和特殊字符的复杂密码"""
    if length < 4:
        length = 4

    upper = string.ascii_uppercase
    lower = string.ascii_lowercase
    digits = string.digits
    special = "!@#$%^&*()_+-=[]{}|;:,.<>?"

    # 确保每类字符至少出现一个
    password_chars = [
        secrets.choice(upper),
        secrets.choice(lower),
        secrets.choice(digits),
        secrets.choice(special),
    ]

    all_chars = upper + lower + digits + special
    password_chars += [secrets.choice(all_chars) for _ in range(length - 4)]

    # 打乱顺序
    result = list(password_chars)
    secrets.SystemRandom().shuffle(result)
    return "".join(result)


def validate_ip_address(ip: str) -> bool:
    """验证 IPv4 地址格式"""
    pattern = r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    return bool(re.match(pattern, ip))


def validate_port(port: int | str) -> bool:
    """验证端口号是否有效（1-65535）"""
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False


def format_datetime(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S") -> str:
    """格式化日期时间"""
    if dt is None:
        return ""
    return dt.strftime(format_str)


def parse_datetime(dt_str: str, format_str: str = "%Y-%m-%d %H:%M:%S") -> Optional[datetime]:
    """解析日期时间字符串"""
    try:
        return datetime.strptime(dt_str, format_str)
    except (ValueError, TypeError):
        return None


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """安全地解析 JSON 字符串"""
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: str = "{}", **kwargs) -> str:
    """安全地序列化对象为 JSON 字符串"""
    try:
        return json.dumps(obj, **kwargs)
    except (TypeError, ValueError):
        return default


def mask_sensitive_data(data: str, mask_char: str = "*", visible_chars: int = 4) -> str:
    """掩码处理敏感数据"""
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else data
    return data[:visible_chars] + mask_char * (len(data) - visible_chars)


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """截断字符串"""
    if not text or len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f}{size_names[i]}"


def generate_random_string(
    length: int = 32,
    include_uppercase: bool = True,
    include_lowercase: bool = True,
    include_digits: bool = True,
    include_special_chars: bool = False,
) -> str:
    """生成随机字符串"""
    chars = ""
    if include_uppercase:
        chars += string.ascii_uppercase
    if include_lowercase:
        chars += string.ascii_lowercase
    if include_digits:
        chars += string.digits
    if include_special_chars:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    if not chars:
        chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def validate_email(email: str) -> bool:
    """验证电子邮件地址格式"""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def is_valid_hostname(hostname: str) -> bool:
    """验证主机名是否有效"""
    if not hostname or len(hostname) > 253:
        return False
    if validate_ip_address(hostname):
        return True
    hostname_pattern = (
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    return bool(re.match(hostname_pattern, hostname))


def chunk_list(lst: list, chunk_size: int) -> list[list]:
    """将列表分块"""
    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]


def format_duration(seconds: float) -> str:
    """格式化持续时间"""
    if seconds < 0:
        return "0秒"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if secs > 0 or not parts:
        parts.append(f"{secs}秒")
    return "".join(parts)


def sanitize_filename(filename: str) -> str:
    """清理文件名，移除不安全的字符"""
    unsafe_chars = ["/", "\\", ":", "*", "?", '"', "<", ">", "|", "\x00"]
    for char in unsafe_chars:
        filename = filename.replace(char, "_")
    filename = filename.strip()
    if not filename:
        filename = "unnamed"
    return filename
