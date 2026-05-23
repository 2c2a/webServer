from django.db import models
from django.conf import settings
from utils.crypto import encrypt_value, decrypt_value
import os


class Host(models.Model):
    """
    主机模型
    """
    OS_TYPE_CHOICES = [
        ('windows', 'Windows'),
    ]

    CONNECTION_TYPE_CHOICES = [
        ('winrm', 'WinRM'),
        ('localwinserver', '本地WinServer'),
        ('ssh', 'SSH'),
        ('tunnel', '隧道模式(零公网IP)'),
    ]

    AUTH_METHOD_CHOICES = [
        ('ntlm', '管理员账户密码'),
        ('certificate', '证书'),
    ]

    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('error', '错误'),
    ]

    TUNNEL_STATUS_CHOICES = [
        ('no_tunnel', '无隧道'),
        ('offline', '隧道离线'),
        ('online', '隧道在线'),
        ('error', '隧道错误'),
    ]

    name = models.CharField(max_length=100, verbose_name='主机名称')
    os_type = models.CharField(max_length=20, choices=OS_TYPE_CHOICES, default='windows', verbose_name='主机系统')
    hostname = models.CharField(max_length=255, verbose_name='主机地址')
    connection_type = models.CharField(max_length=20, choices=CONNECTION_TYPE_CHOICES, default='winrm', verbose_name='连接类型')
    auth_method = models.CharField(max_length=20, choices=AUTH_METHOD_CHOICES, default='ntlm', verbose_name='连接方式')
    port = models.IntegerField(default=5985, verbose_name='连接端口')
    rdp_port = models.IntegerField(default=3389, verbose_name='RDP端口')
    use_ssl = models.BooleanField(default=False, verbose_name='使用SSL')
    username = models.CharField(max_length=100, blank=True, default='', verbose_name='用户名')
    _password = models.CharField(max_length=255, verbose_name='密码', db_column='password')  # 加密存储
    cert_pem_path = models.CharField(max_length=512, blank=True, default='', verbose_name='客户端证书路径')
    cert_key_path = models.CharField(max_length=512, blank=True, default='', verbose_name='客户端私钥路径')
    os_version = models.CharField(max_length=100, blank=True, verbose_name='操作系统版本')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='offline', verbose_name='状态')
    description = models.TextField(blank=True, verbose_name='描述')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='创建者')
    
    # 管理员列表 - 核心字段用于数据隔离
    administrators = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name="授权管理员",
        related_name='managed_hosts'
    )
    
    # 管理提供商 - 由超级管理员分配
    providers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name='管理提供商',
        related_name='provider_hosts',
        help_text='由超级管理员分配的提供商用户，提供商可以管理此主机'
    )
    
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    tunnel_token = models.CharField(
        max_length=64, unique=True, null=True, blank=True,
        verbose_name='隧道Token'
    )
    tunnel_status = models.CharField(
        max_length=20, choices=TUNNEL_STATUS_CHOICES,
        default='no_tunnel', verbose_name='隧道状态'
    )
    tunnel_connected_at = models.DateTimeField(
        null=True, blank=True, verbose_name='隧道连接时间'
    )
    tunnel_last_seen_at = models.DateTimeField(
        null=True, blank=True, verbose_name='隧道最后心跳'
    )
    tunnel_client_version = models.CharField(
        max_length=50, blank=True, verbose_name='隧道客户端版本'
    )
    tunnel_client_ip = models.GenericIPAddressField(
        null=True, blank=True, verbose_name='隧道客户端IP'
    )
    tunnel_public_key = models.TextField(
        blank=True, verbose_name='隧道公钥(Ed25519)'
    )

    class Meta:
        verbose_name = '主机'
        verbose_name_plural = '主机'
        db_table = 'hosts_host'  # 与数据库中的实际表名一致

    def __str__(self):
        return self.name

    @property
    def password(self):
        try:
            return decrypt_value(self._password)
        except ValueError:
            raise ValueError("密码解密失败，数据可能已损坏或密钥已变更")

    @password.setter
    def password(self, raw_password):
        self._password = encrypt_value(raw_password)

    def save(self, *args, **kwargs):
        """
        重写save方法
        注意：连接测试由Admin的save_model处理，避免循环调用
        """
        # 先调用父类的save方法保存数据
        super().save(*args, **kwargs)
        # 暂时禁用自动连接测试，由Admin处理
    
    def get_connection_client(self):
        if self.connection_type == 'winrm':
            from utils.winrm_client import WinrmClient
            kwargs = dict(
                hostname=self.hostname,
                port=self.port,
                use_ssl=self.use_ssl,
            )
            if self.auth_method == 'certificate':
                kwargs.update(
                    auth_method='certificate',
                    cert_pem_path=self.cert_pem_path,
                    cert_key_path=self.cert_key_path,
                    server_cert_validation='ignore',
                )
            else:
                kwargs.update(
                    username=self.username,
                    password=self.password,
                    auth_method='ntlm',
                )
            return WinrmClient(**kwargs)
        elif self.connection_type == 'localwinserver':
            from utils.local_winserver_client import LocalWinServerClient
            return LocalWinServerClient(
                username=self.username,
                password=self.password
            )
        elif self.connection_type == 'tunnel':
            from utils.gateway_client import GatewayClient
            return TunnelConnectionAdapter(self, GatewayClient())
        elif self.connection_type == 'ssh':
            raise NotImplementedError("SSH连接类型尚未实现")
        else:
            raise ValueError(
                f"不支持的连接类型: {self.connection_type}"
            )

    def test_connection(self):
        if os.environ.get('2C2A_DEMO', '').lower() == '1':
            Host.objects.filter(pk=self.pk).update(status='online')
            return

        if self.connection_type == 'tunnel':
            new_status = 'online' if self.tunnel_status == 'online' else 'offline'
            Host.objects.filter(pk=self.pk).update(status=new_status)
            return

        if (self.auth_method == 'certificate'
                and (not self.cert_pem_path
                     or not os.path.exists(self.cert_pem_path))):
            import logging
            logging.getLogger("2c2a").warning(
                f"证书文件不存在，跳过连接测试: {self.name} "
                f"(pem={self.cert_pem_path})"
            )
            Host.objects.filter(pk=self.pk).update(status='pending')
            return
        
        try:
            client = self.get_connection_client()
            
            if self.connection_type == 'localwinserver':
                result = client.execute_command(
                    'echo Connection Test OK'
                )
            else:
                result = client.execute_command('whoami')
            
            if result.success:
                new_status = 'online'
            else:
                new_status = 'error'
                
        except Exception as e:
            new_status = 'error'
            import logging
            logger = logging.getLogger("2c2a")
            logger.error(
                f"测试主机连接失败: {self.name}, 错误: {str(e)}"
            )
        
        Host.objects.filter(pk=self.pk).update(status=new_status)


class TunnelConnectionAdapter:
    def __init__(self, host, gateway_client):
        self.host = host
        self.gateway_client = gateway_client
        self._fallback_client = None

    def _get_fallback_client(self):
        if self._fallback_client is not None:
            return self._fallback_client
        if self.host.connection_type == 'tunnel' and self.host.hostname:
            try:
                from utils.winrm_client import WinrmClient
                self._fallback_client = WinrmClient(
                    hostname=self.host.hostname,
                    port=self.host.port,
                    username=self.host.username,
                    password=self.host.password,
                    use_ssl=self.host.use_ssl,
                )
                return self._fallback_client
            except Exception:
                pass
        return None

    @property
    def success(self):
        return True

    def execute_command(self, command, arguments=None):
        return self.execute_powershell(command)

    def execute_powershell(self, script, arguments=None):
        script_bytes = script.encode('utf-8')

        result = self.gateway_client.remote_exec(
            token=self.host.tunnel_token,
            script=script_bytes,
        )

        if result is None:
            fallback = self._get_fallback_client()
            if fallback:
                return fallback.execute_powershell(script)
            from utils.winrm_client import WinrmResult
            return WinrmResult(
                status_code=1,
                std_out='',
                std_err='Gateway不可用且无备用连接方式'
            )

        from utils.winrm_client import WinrmResult
        stdout = ''
        stderr = ''
        exit_code = 1

        if result.get('success'):
            data = result.get('data', {})
            if isinstance(data, dict):
                stdout = data.get('stdout', '')
                stderr = data.get('stderr', '')
                exit_code = data.get('exit_code', 1)
                if isinstance(stdout, bytes):
                    stdout = stdout.decode('utf-8', errors='ignore')
                if isinstance(stderr, bytes):
                    stderr = stderr.decode('utf-8', errors='ignore')

        return WinrmResult(
            status_code=exit_code,
            std_out=stdout,
            std_err=stderr,
        )

    def create_user(self, username, password, description=None, group=None):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        safe_desc = _escape_ps_string(description or '')

        script = f'''
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
New-LocalUser -Name "{safe_user}" -Password $pw -Description "{safe_desc}" -ErrorAction Stop
Add-LocalGroupMember -Group "Users" -Member "{safe_user}" -ErrorAction Stop
'''
        if group:
            safe_group = _escape_ps_string(group)
            script += f'Add-LocalGroupMember -Group "{safe_group}" -Member "{safe_user}" -ErrorAction Stop\n'

        result = self.execute_powershell(script)
        self.add_to_remote_users(username)
        return result

    def delete_user(self, username):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        script = f'Remove-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        return self.execute_powershell(script)

    def enable_user(self, username):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        script = f'Enable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        return self.execute_powershell(script)

    def disabled_user(self, username):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        script = f'Disable-LocalUser -Name "{safe_user}" -ErrorAction Stop'
        return self.execute_powershell(script)

    def reset_password(self, username, password):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        safe_pass = _escape_ps_string(password)
        script = f'''
$pw = ConvertTo-SecureString "{safe_pass}" -AsPlainText -Force
Set-LocalUser -Name "{safe_user}" -Password $pw
'''
        result = self.execute_powershell(script)
        if result.status_code == 0:
            self.add_to_remote_users(username)
        return result

    def add_to_remote_users(self, username):
        from utils.winrm_client import _escape_ps_string
        safe_user = _escape_ps_string(username)
        script = (
            f'Add-LocalGroupMember -Group "Remote Desktop Users" '
            f'-Member "{safe_user}" -ErrorAction SilentlyContinue'
        )
        return self.execute_powershell(script)


class HostGroup(models.Model):
    """
    主机组模型
    用于将多个主机分组管理
    """
    name = models.CharField(max_length=100, verbose_name='组名称')
    description = models.TextField(blank=True, verbose_name='描述')
    hosts = models.ManyToManyField(Host, blank=True, verbose_name='主机')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='创建者',
        related_name='created_hostgroups'
    )
    # 管理提供商 - 由超级管理员分配
    providers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        verbose_name='管理提供商',
        related_name='provider_hostgroups',
        help_text='由超级管理员分配的提供商用户，提供商可以管理此主机组'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    class Meta:
        verbose_name = '主机组'
        verbose_name_plural = '主机组'
        db_table = 'hosts_hostgroup'

    def __str__(self):
        return self.name