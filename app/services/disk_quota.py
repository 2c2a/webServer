"""
磁盘配额管理服务

通过 WinRM 或本地客户端管理 Windows 磁盘配额。
"""
import json
import logging
import os
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

DISK_LETTER_PATTERN = re.compile(r'^[A-Za-z]:\\?$')
MB_TO_BYTES = 1024 * 1024


def validate_disk_letter(disk_letter: str) -> str:
    """验证磁盘盘符格式"""
    disk_letter = disk_letter.strip().upper()
    if not DISK_LETTER_PATTERN.match(disk_letter):
        raise ValueError(f"无效的磁盘盘符: {disk_letter}")
    return disk_letter.rstrip('\\')


def validate_quota_value(value: Any, field_name: str = "配额值") -> int:
    """验证配额值"""
    try:
        v = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name}必须为数字")
    if v < 0:
        raise ValueError(f"{field_name}不能为负数")
    return v


def get_disk_info_via_client(client) -> list[dict[str, Any]]:
    """
    通过客户端获取磁盘信息列表

    Args:
        client: WinrmClient 或 LocalWinServerClient 实例

    Returns:
        磁盘信息列表，每项包含 drive, total_mb, free_mb
    """
    if os.environ.get('2C2A_DEMO', '').lower() == '1':
        logger.info("DEMO模式: 返回模拟磁盘信息")
        return [
            {"drive": "C:", "total_mb": 102400, "free_mb": 51200},
            {"drive": "D:", "total_mb": 204800, "free_mb": 102400},
        ]

    script = '''
$disks = Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3"
$result = @()
foreach ($disk in $disks) {
    $result += [PSCustomObject]@{
        Drive = $disk.DeviceID
        TotalMB = [math]::Round($disk.Size / 1MB)
        FreeMB = [math]::Round($disk.FreeSpace / 1MB)
    }
}
$result | ConvertTo-Json -Compress
'''
    try:
        result = client.execute_powershell(script)
        if result.status_code == 0 and result.std_out.strip():
            output = result.std_out.strip()
            try:
                disks = json.loads(output)
            except json.JSONDecodeError:
                disks = []

            if isinstance(disks, dict):
                disks = [disks]

            disk_list = []
            for d in disks:
                disk_list.append({
                    "drive": d.get("Drive", ""),
                    "total_mb": d.get("TotalMB", 0),
                    "free_mb": d.get("FreeMB", 0),
                })
            return disk_list
        else:
            logger.error("获取磁盘信息失败: %s", result.std_err)
            return []
    except Exception as e:
        logger.error("获取磁盘信息异常: %s", str(e))
        return []


def set_disk_quota_via_client(
    client,
    username: str,
    disk_letter: str,
    quota_mb: int,
    warning_mb: Optional[int] = None,
) -> dict[str, Any]:
    """
    通过客户端设置磁盘配额

    Args:
        client: WinrmClient 或 LocalWinServerClient 实例
        username: Windows 用户名
        disk_letter: 磁盘盘符，如 "C:"
        quota_mb: 配额大小（MB）
        warning_mb: 警告阈值（MB），默认为配额的80%

    Returns:
        {"success": bool, "message": str}
    """
    validate_disk_letter(disk_letter)
    validate_quota_value(quota_mb, "配额大小")

    if warning_mb is None:
        warning_mb = int(quota_mb * 0.8)
    else:
        validate_quota_value(warning_mb, "警告阈值")

    if os.environ.get('2C2A_DEMO', '').lower() == '1':
        logger.info("DEMO模式: 模拟设置用户 %s 在 %s 的配额为 %dMB", username, disk_letter, quota_mb)
        return {"success": True, "message": f"DEMO模式: 已设置用户 {username} 在 {disk_letter} 的配额为 {quota_mb}MB"}

    disk_letter = disk_letter.upper().rstrip('\\')
    quota_bytes = quota_mb * MB_TO_BYTES
    warning_bytes = warning_mb * MB_TO_BYTES

    script = f'''
$ErrorActionPreference = 'Stop'
$drive = "{disk_letter}"
$username = "{username}"
$quotaBytes = [long]{quota_bytes}
$warningBytes = [long]{warning_bytes}

try {{
    $vol = Get-CimInstance Win32_Volume -Filter "DriveLetter='$drive'" -ErrorAction Stop
    if (-not $vol) {{
        Write-Error "找不到卷 $drive"
        exit 1
    }}

    if (-not $vol.QuotasEnabled) {{
        $enforceOutput = & fsutil quota enforce $drive 2>&1
        if ($LASTEXITCODE -ne 0) {{
            Write-Error "启用配额失败: $enforceOutput"
            exit 1
        }}
        $vol = Get-CimInstance Win32_Volume -Filter "DriveLetter='$drive'" -ErrorAction Stop
        if (-not $vol.QuotasEnabled) {{
            Write-Error "无法启用卷 $drive 的磁盘配额"
            exit 1
        }}
    }}

    $user = Get-LocalUser -Name $username -ErrorAction SilentlyContinue
    if (-not $user) {{
        $user = Get-CimInstance Win32_UserAccount -Filter "Name='$username'" -ErrorAction SilentlyContinue
        if (-not $user) {{
            Write-Error "用户 $username 不存在"
            exit 1
        }}
    }}

    $modifyOutput = & fsutil quota modify $drive $warningBytes $quotaBytes $username 2>&1
    if ($LASTEXITCODE -ne 0) {{
        Write-Error "设置用户配额失败: $modifyOutput"
        exit 1
    }}

    Write-Output "SUCCESS"
}} catch {{
    Write-Error $_.Exception.Message
    exit 1
}}
'''
    try:
        result = client.execute_powershell(script)
        if result.status_code == 0 and "SUCCESS" in result.std_out:
            logger.info("设置磁盘配额成功: 用户=%s, 磁盘=%s, 配额=%dMB", username, disk_letter, quota_mb)
            return {"success": True, "message": f"已设置用户 {username} 在 {disk_letter} 的配额为 {quota_mb}MB"}
        else:
            error_msg = result.std_err.strip() if result.std_err else "未知错误"
            logger.error("设置磁盘配额失败: %s", error_msg)
            return {"success": False, "message": f"设置磁盘配额失败: {error_msg}"}
    except Exception as e:
        logger.error("设置磁盘配额异常: %s", str(e))
        return {"success": False, "message": f"设置磁盘配额异常: {str(e)}"}


def set_user_disk_quotas(
    client,
    username: str,
    disk_quota: dict[str, int],
) -> dict[str, Any]:
    """
    批量设置用户磁盘配额

    Args:
        client: WinrmClient 或 LocalWinServerClient 实例
        username: Windows 用户名
        disk_quota: 配额配置，如 {"C:": 10240, "D:": 20480}

    Returns:
        {"success": bool, "results": list, "errors": list}
    """
    results = []
    errors = []

    for disk_letter, quota_mb in disk_quota.items():
        try:
            validate_quota_value(quota_mb, f"磁盘 {disk_letter} 配额")
            result = set_disk_quota_via_client(client, username, disk_letter, quota_mb)
            results.append({"disk": disk_letter, "result": result})
            if not result["success"]:
                errors.append(f"{disk_letter}: {result['message']}")
        except ValueError as e:
            errors.append(f"{disk_letter}: {str(e)}")

    return {
        "success": len(errors) == 0,
        "results": results,
        "errors": errors,
    }
