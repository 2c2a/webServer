"""
辅助函数模块
提供项目中常用的辅助函数
"""
import re
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from django.utils import timezone
from django.conf import settings


def get_client_ip(request) -> Optional[str]:
    """获取客户端真实 IP 地址（支持 nginx 反向代理）

    优先级：
    1. 当请求来自可信代理时，依次尝试 X-Forwarded-For（取第一个非可信 IP）、X-Real-IP
    2. 否则直接使用 REMOTE_ADDR
    """
    remote_addr = request.META.get('REMOTE_ADDR', '')

    # 检查请求是否来自可信代理
    trusted_proxies = getattr(settings, 'TRUSTED_PROXY_IPS', None)
    if trusted_proxies and remote_addr in trusted_proxies:
        # X-Forwarded-For: client, proxy1, proxy2 — 取最右边的非可信 IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ips = [ip.strip() for ip in x_forwarded_for.split(',')]
            # 从右往左找第一个非可信代理的 IP
            for ip in reversed(ips):
                if ip not in trusted_proxies:
                    return ip
            # 全部都是可信代理，取最左边的
            return ips[0]

        # 尝试 X-Real-IP（nginx 默认设置）
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip.strip()

    # 兼容旧配置 USE_X_FORWARDED_FOR
    if getattr(settings, 'USE_X_FORWARDED_FOR', False):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()

    return remote_addr or None


def validate_ip_address(ip: str) -> bool:
    """
    验证IP地址格式是否正确

    Args:
        ip: 待验证的IP地址字符串

    Returns:
        bool: IP地址格式是否有效
    """
    pattern = r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
    return bool(re.match(pattern, ip))


def validate_port(port: Union[int, str]) -> bool:
    """
    验证端口号是否有效

    Args:
        port: 待验证的端口号

    Returns:
        bool: 端口号是否有效（1-65535）
    """
    try:
        port_num = int(port)
        return 1 <= port_num <= 65535
    except (ValueError, TypeError):
        return False


def format_datetime(dt: datetime, format_str: str = '%Y-%m-%d %H:%M:%S') -> str:
    """
    格式化日期时间

    Args:
        dt: 日期时间对象
        format_str: 格式化字符串，默认为 '%Y-%m-%d %H:%M:%S'

    Returns:
        str: 格式化后的日期时间字符串
    """
    if dt is None:
        return ''
    return dt.strftime(format_str)


def parse_datetime(dt_str: str, format_str: str = '%Y-%m-%d %H:%M:%S') -> Optional[datetime]:
    """
    解析日期时间字符串

    Args:
        dt_str: 日期时间字符串
        format_str: 格式化字符串，默认为 '%Y-%m-%d %H:%M:%S'

    Returns:
        datetime: 解析后的日期时间对象，如果解析失败则返回None
    """
    try:
        return datetime.strptime(dt_str, format_str)
    except (ValueError, TypeError):
        return None


def get_time_range(days: int = 7) -> tuple:
    """
    获取指定天数的时间范围

    Args:
        days: 天数，默认为7天

    Returns:
        tuple: (开始时间, 结束时间) 的元组
    """
    end_time = timezone.now()
    start_time = end_time - timedelta(days=days)
    return start_time, end_time


def safe_json_loads(json_str: str, default: Any = None) -> Any:
    """
    安全地解析JSON字符串

    Args:
        json_str: JSON字符串
        default: 解析失败时的默认返回值

    Returns:
        解析后的对象或默认值
    """
    try:
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return default


def safe_json_dumps(obj: Any, default: str = '{}', **kwargs) -> str:
    """
    安全地序列化对象为JSON字符串

    Args:
        obj: 待序列化的对象
        default: 序列化失败时的默认返回值
        **kwargs: 传递给json.dumps的额外参数

    Returns:
        str: JSON字符串或默认值
    """
    try:
        return json.dumps(obj, **kwargs)
    except (TypeError, ValueError):
        return default


def mask_sensitive_data(data: str, mask_char: str = '*', visible_chars: int = 4) -> str:
    """
    掩码处理敏感数据

    Args:
        data: 待处理的字符串
        mask_char: 掩码字符，默认为 '*'
        visible_chars: 保留可见的字符数，默认为4

    Returns:
        str: 掩码处理后的字符串
    """
    if not data or len(data) <= visible_chars:
        return mask_char * len(data) if data else data

    return data[:visible_chars] + mask_char * (len(data) - visible_chars)


def truncate_string(text: str, max_length: int = 100, suffix: str = '...') -> str:
    """
    截断字符串

    Args:
        text: 待截断的字符串
        max_length: 最大长度，默认为100
        suffix: 截断后添加的后缀，默认为 '...'

    Returns:
        str: 截断后的字符串
    """
    if not text or len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        str: 格式化后的文件大小字符串
    """
    if size_bytes == 0:
        return '0B'

    size_names = ['B', 'KB', 'MB', 'GB', 'TB']
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1

    return f'{size_bytes:.2f}{size_names[i]}'


def generate_random_string(length: int = 32, 
                          include_uppercase: bool = True,
                          include_lowercase: bool = True,
                          include_digits: bool = True,
                          include_special_chars: bool = False) -> str:
    """
    生成随机字符串

    Args:
        length: 字符串长度，默认为32
        include_uppercase: 是否包含大写字母，默认为True
        include_lowercase: 是否包含小写字母，默认为True
        include_digits: 是否包含数字，默认为True
        include_special_chars: 是否包含特殊字符，默认为False

    Returns:
        str: 生成的随机字符串
    """
    import secrets as _secrets
    import string

    chars = ''
    if include_uppercase:
        chars += string.ascii_uppercase
    if include_lowercase:
        chars += string.ascii_lowercase
    if include_digits:
        chars += string.digits
    if include_special_chars:
        chars += '!@#$%^&*()_+-=[]{}|;:,.<>?'

    if not chars:
        chars = string.ascii_letters + string.digits

    return ''.join(_secrets.choice(chars) for _ in range(length))


def validate_email(email: str) -> bool:
    """
    验证电子邮件地址格式

    Args:
        email: 待验证的电子邮件地址

    Returns:
        bool: 电子邮件地址格式是否有效
    """
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def is_valid_hostname(hostname: str) -> bool:
    """
    验证主机名是否有效

    Args:
        hostname: 待验证的主机名

    Returns:
        bool: 主机名是否有效
    """
    if not hostname or len(hostname) > 253:
        return False

    # 检查是否为IP地址
    if validate_ip_address(hostname):
        return True

    # 检查主机名格式
    hostname_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
    return bool(re.match(hostname_pattern, hostname))


def get_setting(key: str, default: Any = None) -> Any:
    """
    获取Django设置值

    Args:
        key: 设置键名
        default: 默认值

    Returns:
        设置值或默认值
    """
    return getattr(settings, key, default)


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    将列表分块

    Args:
        lst: 待分块的列表
        chunk_size: 每块的大小

    Returns:
        List[List[Any]]: 分块后的列表
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def merge_dicts(*dicts: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    合并多个字典

    Args:
        *dicts: 待合并的字典

    Returns:
        Dict[Any, Any]: 合并后的字典
    """
    result = {}
    for d in dicts:
        if isinstance(d, dict):
            result.update(d)
    return result


def deep_update_dict(base_dict: Dict[Any, Any], 
                    update_dict: Dict[Any, Any]) -> Dict[Any, Any]:
    """
    深度更新字典

    Args:
        base_dict: 基础字典
        update_dict: 更新字典

    Returns:
        Dict[Any, Any]: 更新后的字典
    """
    for key, value in update_dict.items():
        if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
            base_dict[key] = deep_update_dict(base_dict[key], value)
        else:
            base_dict[key] = value
    return base_dict


def format_duration(seconds: float) -> str:
    """
    格式化持续时间

    Args:
        seconds: 持续时间（秒）

    Returns:
        str: 格式化后的持续时间字符串
    """
    if seconds < 0:
        return '0秒'

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    parts = []
    if hours > 0:
        parts.append(f'{hours}小时')
    if minutes > 0:
        parts.append(f'{minutes}分钟')
    if secs > 0 or not parts:
        parts.append(f'{secs}秒')

    return ''.join(parts)


def is_valid_url(url: str) -> bool:
    """
    验证URL是否有效

    Args:
        url: 待验证的URL

    Returns:
        bool: URL是否有效
    """
    pattern = r'^https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w .-]*/?$'
    return bool(re.match(pattern, url))


def sanitize_filename(filename: str) -> str:
    """
    清理文件名，移除不安全的字符

    Args:
        filename: 待清理的文件名

    Returns:
        str: 清理后的文件名
    """
    # 移除路径分隔符和其他危险字符
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\x00']
    for char in unsafe_chars:
        filename = filename.replace(char, '_')

    # 移除前后空格
    filename = filename.strip()

    # 确保文件名不为空
    if not filename:
        filename = 'unnamed'

    return filename
