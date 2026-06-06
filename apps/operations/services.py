"""
业务逻辑服务层
将复杂的业务逻辑从业务视图和Admin中抽离出来，提供统一的服务接口
"""
import logging
from django.db import transaction
from .models import CloudComputerUser

logger = logging.getLogger(__name__)


def execute_account_opening(account_request):
    """
    执行开户操作：通过 WinRM 在目标主机上创建用户
    
    Args:
        account_request: AccountOpeningRequest 实例
    
    Raises:
        Exception: 连接或执行失败时抛出
    """
    with transaction.atomic():
        try:
            # 记录开始处理
            logger.info(f"开始处理开户申请: {account_request.username}")
            account_request.start_processing()
            
            # 系统生成强密码
            password = CloudComputerUser.generate_complex_password()
            
            # 连接到目标主机
            host = account_request.target_product.host
            client = host.get_connection_client()
            
            # 执行远程用户创建
            result = client.create_user(account_request.username, password)
            
            if result.status_code == 0:
                # 计算用户磁盘配额
                user_disk_quota = {}
                product = account_request.target_product
                if product.enable_disk_quota and product.default_disk_quota:
                    user_disk_quota = dict(product.default_disk_quota)
                    if account_request.requested_disk_capacity:
                        for disk, capacity in account_request.requested_disk_capacity.items():
                            if disk in product.allow_extra_quota_disks:
                                user_disk_quota[disk] = capacity

                # 设置磁盘配额
                if user_disk_quota:
                    try:
                        from utils.disk_quota import set_user_disk_quotas
                        quota_result = set_user_disk_quotas(
                            client, account_request.username, user_disk_quota
                        )
                        if not quota_result['success']:
                            logger.warning(
                                f"磁盘配额设置部分失败: "
                                f"{quota_result.get('errors', [])}"
                            )
                    except Exception as e:
                        logger.error(f"磁盘配额设置失败: {str(e)}")

                # 成功创建用户
                cloud_user, created = CloudComputerUser.objects.get_or_create(
                    username=account_request.username,
                    product=account_request.target_product,
                    defaults={
                        'fullname': account_request.user_fullname,
                        'email': account_request.user_email,
                        'description': account_request.user_description,
                        'created_from_request': account_request,
                        'initial_password': password,
                        'disk_quota': user_disk_quota,
                    }
                )
                
                # 更新申请状态
                account_request.complete(
                    cloud_user_id=account_request.username,
                    cloud_user_password='',
                    result_message=f"用户 {account_request.username} 已成功创建"
                )
                
                logger.info(f"开户申请处理成功: {account_request.username}")
                return True
            else:
                # 创建用户失败
                error_msg = result.std_err if result.std_err else '未知错误'
                account_request.fail("开户处理失败，请联系管理员了解详情")
                logger.error(f"开户申请处理失败: {account_request.username}, 错误: {error_msg}")
                raise Exception(f"创建用户失败: {error_msg}")

        except Exception as e:
            # 处理过程中的任何异常
            error_msg = str(e)
            account_request.fail("开户处理失败，请联系管理员了解详情")
            logger.error(f"开户申请处理异常: {account_request.username}, 异常: {error_msg}")
            raise


def update_user_admin_permission(cloud_user, make_admin):
    """
    更新用户的管理员权限
    
    Args:
        cloud_user: CloudComputerUser 实例
        make_admin: bool, True表示授予管理员权限，False表示撤销
    
    Raises:
        Exception: 权限操作失败时抛出
    """
    try:
        # 连接到产品关联的主机
        product = cloud_user.product
        host = product.host
        client = host.get_connection_client()
        
        if make_admin:
            # 授予管理员权限
            success = client.op_user(cloud_user.username)
            if not success:
                raise Exception(f"为用户 {cloud_user.username} 授予管理员权限失败")
        else:
            # 剥夺管理员权限
            success = client.deop_user(cloud_user.username)
            if not success:
                raise Exception(f"撤销用户 {cloud_user.username} 的管理员权限失败")
                
        logger.info(f"{'授予' if make_admin else '撤销'}用户 {cloud_user.username} 管理员权限成功")
        return True
        
    except Exception as e:
        logger.error(f"更新用户管理员权限失败: {cloud_user.username}, 错误: {str(e)}")
        raise


def get_user_password_and_burn(cloud_user):
    """
    获取用户密码并销毁（阅后即焚）
    
    Args:
        cloud_user: CloudComputerUser 实例
    
    Returns:
        str: 用户密码
    
    Raises:
        Exception: 获取密码失败时抛出
    """
    try:
        password = cloud_user.get_and_burn_password()
        logger.info(f"用户 {cloud_user.username} 成功获取并销毁初始密码")
        return password
    except Exception as e:
        logger.error(f"获取用户 {cloud_user.username} 密码失败: {str(e)}")
        raise


def toggle_user_status(cloud_user, action):
    """
    切换用户状态
    
    Args:
        cloud_user: CloudComputerUser 实例
        action: str, 操作类型 ('activate', 'deactivate', 'disable', 'delete')
    
    Returns:
        bool: 操作是否成功
    
    Raises:
        Exception: 状态切换失败时抛出
    """
    try:
        if action == 'activate':
            cloud_user.activate()
        elif action == 'deactivate':
            cloud_user.deactivate()
        elif action == 'disable':
            cloud_user.disable()
        elif action == 'delete':
            cloud_user.delete_user()
        else:
            raise ValueError(f"无效的操作类型: {action}")
            
        logger.info(f"用户 {cloud_user.username} 状态切换成功: {action}")
        return True
        
    except Exception as e:
        logger.error(f"切换用户 {cloud_user.username} 状态失败: {action}, 错误: {str(e)}")
        raise