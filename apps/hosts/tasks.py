from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone

from apps.hosts.models import Host
from apps.tasks.models import AsyncTask
import logging
import re

logger = logging.getLogger(__name__)

CERT_THUMBPRINT_PATTERN = re.compile(r'^[A-Fa-f0-9]{40}$')
CERT_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]{1,255}\.pem$')


def validate_cert_thumbprint(thumbprint: str) -> str:
    if not thumbprint:
        raise ValueError("证书指纹不能为空")
    thumbprint = thumbprint.strip().upper()
    if not CERT_THUMBPRINT_PATTERN.match(thumbprint):
        raise ValueError("证书指纹格式无效，必须是40位十六进制字符")
    return thumbprint


def validate_cert_filename(filename: str) -> str:
    if not filename:
        raise ValueError("证书文件名不能为空")
    if not CERT_FILENAME_PATTERN.match(filename):
        raise ValueError("证书文件名格式无效，只允许字母、数字、下划线、连字符和点，且必须以.pem结尾")
    return filename


def validate_cert_content(content: str) -> str:
    if not content:
        raise ValueError("证书内容不能为空")
    if '@"' in content or '"@' in content:
        raise ValueError("证书内容包含非法字符")
    if len(content) > 100000:
        raise ValueError("证书内容过长")
    return content


@shared_task(bind=True)
def configure_winrm_on_host(self, host_id, cert_thumbprint=None, operator_id=None):
    task = AsyncTask.objects.create(
        task_id=self.request.id,
        name=f"配置WinRM - 主机 #{host_id}",
        created_by_id=operator_id,
        target_object_id=host_id,
        target_content_type='hosts.Host',
        status='running'
    )
    
    try:
        host = Host.objects.get(id=host_id)
        task.start_execution()
        
        task.progress = 10
        task.save()
        
        try:
            from utils.winrm_client import WinrmClient
            
            client = WinrmClient(
                hostname=host.hostname or host.ip_address,
                port=host.port,
                username=host.username,
                password=host.password,
                use_ssl=host.use_ssl
            )
            
            actual_thumbprint = cert_thumbprint or host.certificate_thumbprint
            if actual_thumbprint:
                actual_thumbprint = validate_cert_thumbprint(actual_thumbprint)
            
            ps_script = '''
            Enable-PSRemoting -Force
            Set-Service -Name WinRM -StartupType Automatic
            '''
            
            if actual_thumbprint:
                ps_script += f'''
                $selectorset = @{{Transport="HTTPS"}}
                $resourceset = @{{Port="5986"; CertificateThumbprint="{actual_thumbprint}"}}
                Get-WSManInstance -ResourceURI winrm/config/listener -SelectorSet $selectorset -ErrorAction SilentlyContinue | Remove-WSManInstance -ErrorAction SilentlyContinue
                New-WSManInstance -ResourceURI winrm/config/listener -SelectorSet $selectorset -ValueSet $resourceset
                if (-not (Get-NetFirewallRule -Name "WinRM-HTTPS-In-TCP-Public" -ErrorAction SilentlyContinue)) {{
                    New-NetFirewallRule -Name "WinRM-HTTPS-In-TCP-Public" -DisplayName "WinRM HTTPS Inbound" -Enabled True -Direction Inbound -Protocol TCP -LocalPort 5986 -Action Allow -Profile Public,Private,Domain
                }}
                '''
            
            ps_script += '''
            Set-Item -Path "WSMan:\\localhost\\Service\\AllowUnencrypted" -Value $false
            Set-Item -Path "WSMan:\\localhost\\Service\\Auth\\Basic" -Value $true
            Restart-Service WinRM
            '''
            
            task.progress = 30
            task.save()
            
            result = client.execute_powershell(ps_script)
            
            if result.status_code == 0:
                task.progress = 80
                task.save()
                
                from django.utils import timezone
                host.init_status = 'ready'
                host.initialized_at = timezone.now()
                if cert_thumbprint:
                    host.certificate_thumbprint = cert_thumbprint
                host.save()
                
                task.progress = 100
                task.complete_success({
                    'status_code': result.status_code,
                    'stdout': result.std_out,
                    'success': True
                })
                
                return {
                    'success': True,
                    'status_code': result.status_code,
                    'host_id': host_id
                }
            else:
                error_msg = result.std_err if result.std_err else 'Unknown error'
                task.complete_failure(f"PowerShell script failed: {error_msg}")
                
                return {
                    'success': False,
                    'status_code': result.status_code,
                    'error': error_msg
                }
                
        except Exception as conn_error:
            logger.error(f"连接主机失败: {str(conn_error)}", exc_info=True)
            task.complete_failure(f"无法连接到主机: {str(conn_error)}")
            
            return {
                'success': False,
                'error': str(conn_error)
            }
        
    except Exception as e:
        logger.error(f"配置WinRM失败: {str(e)}", exc_info=True)
        task.complete_failure(str(e))
        
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(bind=True)
def test_winrm_connection(self, host_id, use_certificate_auth=False):
    task = AsyncTask.objects.create(
        task_id=self.request.id,
        name=f"测试WinRM连接 - 主机 #{host_id}",
        target_object_id=host_id,
        target_content_type='hosts.Host',
        status='running'
    )

    try:
        host = Host.objects.get(id=host_id)
        task.start_execution()

        old_status = host.status
        host.test_connection()
        host.refresh_from_db()
        new_status = host.status
        success = new_status == 'online'

        if success:
            if host.auth_method == 'certificate' and host.cert_provision_status in ('pending', 'ready'):
                Host.objects.filter(pk=host.pk).update(
                    cert_provision_status='configured',
                    cert_activated_at=timezone.now(),
                )
            status_display = dict(Host.STATUS_CHOICES).get(new_status, new_status)
            task.progress = 100
            task.complete_success({
                'connected': True,
                'status': new_status,
                'status_display': status_display,
                'old_status': old_status,
                'message': f'连接成功，主机状态: {status_display}',
            })

            return {
                'success': True,
                'connected': True,
                'status': new_status,
                'status_display': status_display,
            }
        else:
            if host.auth_method == 'certificate' and host.cert_provision_status in ('pending', 'ready'):
                Host.objects.filter(pk=host.pk).update(cert_provision_status='failed')
            status_display = dict(Host.STATUS_CHOICES).get(new_status, new_status)
            task.complete_failure(f"连接测试失败，主机状态: {status_display}")
            return {
                'success': False,
                'connected': False,
                'status': new_status,
                'status_display': status_display,
                'error': f'连接失败，主机状态: {status_display}',
            }

    except Exception as e:
        logger.error(f"测试WinRM连接失败: {str(e)}", exc_info=True)
        try:
            host = Host.objects.get(id=host_id)
            if host.auth_method == 'certificate' and host.cert_provision_status in ('pending', 'ready'):
                Host.objects.filter(pk=host.pk).update(cert_provision_status='failed')
            Host.objects.filter(pk=host.pk).update(status='error')
        except Host.DoesNotExist:
            pass
        task.complete_failure(str(e))

        return {
            'success': False,
            'connected': False,
            'error': str(e)
        }


@shared_task(bind=True)
def test_winrm_connection_raw(self, connection_type, hostname, port, use_ssl, auth_method, username, password):
    task = AsyncTask.objects.create(
        task_id=self.request.id,
        name=f"测试WinRM连接 - {hostname}",
        status='running'
    )

    try:
        task.start_execution()

        if connection_type == 'localwinserver':
            from utils.local_winserver_client import LocalWinServerClient
            client = LocalWinServerClient(
                username=username,
                password=password,
            )
            result = client.execute_command('echo Connection Test OK')
        elif connection_type == 'winrm' and auth_method == 'ntlm':
            from utils.winrm_client import WinrmClient
            client = WinrmClient(
                hostname=hostname,
                port=int(port),
                username=username,
                password=password,
                use_ssl=bool(use_ssl),
                auth_method='ntlm',
            )
            result = client.execute_command('whoami')
        else:
            raise ValueError(f'不支持的连接类型: {connection_type}')

        if result.success:
            output = result.std_out.strip() if result.std_out else ''
            task.progress = 100
            task.complete_success({
                'connected': True,
                'output': output,
                'message': f'连接成功{f" ({output})" if output else ""}',
            })

            return {
                'success': True,
                'connected': True,
                'output': output,
                'message': f'连接成功{f" ({output})" if output else ""}',
            }
        else:
            error_detail = result.std_err.strip() if result.std_err else f'命令执行返回非零状态码: {result.status_code}'
            task.complete_failure(f"连接失败: {error_detail}")
            return {
                'success': False,
                'connected': False,
                'error': f'连接失败: {error_detail}',
            }

    except Exception as e:
        logger.error(f"测试WinRM连接失败: {hostname}, 错误: {str(e)}", exc_info=True)
        task.complete_failure(str(e))

        return {
            'success': False,
            'connected': False,
            'error': f'连接测试失败: {str(e)}',
        }


@shared_task(bind=True)
def install_certificates_on_host(self, host_id, cert_pem, cert_filename, operator_id=None):
    task = AsyncTask.objects.create(
        task_id=self.request.id,
        name=f"安装证书 - 主机 #{host_id}",
        created_by_id=operator_id,
        target_object_id=host_id,
        target_content_type='hosts.Host',
        status='running'
    )
    
    try:
        host = Host.objects.get(id=host_id)
        task.start_execution()
        
        cert_filename = validate_cert_filename(cert_filename)
        cert_pem = validate_cert_content(cert_pem)
        
        from utils.winrm_client import WinrmClient, _escape_for_here_string
        
        client = WinrmClient(
            hostname=host.hostname or host.ip_address,
            port=host.port,
            username=host.username,
            password=host.password,
            use_ssl=host.use_ssl
        )
        
        safe_cert_content = _escape_for_here_string(cert_pem)
        safe_filename = cert_filename.replace('"', '').replace("'", '').replace(';', '')
        
        ps_script = f'''
        $tempDir = "$env:TEMP\\2c2a_Certs"
        if (!(Test-Path $tempDir)) {{
            New-Item -ItemType Directory -Path $tempDir -Force
        }}
        
        $certContent = @"
{safe_cert_content}
"@
        
        $certPath = Join-Path $tempDir "{safe_filename}"
        $certContent | Out-File -FilePath $certPath -Encoding UTF8
        
        Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\\LocalMachine\\Root
        Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\\LocalMachine\\My
        
        Write-Output "Certificate installed successfully"
        
        Remove-Item $tempDir -Recurse -Force
        '''
        
        result = client.execute_powershell(ps_script)
        
        if result.status_code == 0:
            task.progress = 100
            task.complete_success({
                'installed': True,
                'cert_filename': cert_filename,
                'output': result.std_out
            })
            
            return {
                'success': True,
                'installed': True
            }
        else:
            error_msg = result.std_err if result.std_err else 'Unknown error'
            task.complete_failure(f"Certificate installation failed: {error_msg}")
            
            return {
                'success': False,
                'installed': False,
                'error': error_msg
            }
        
    except Exception as e:
        logger.error(f"安装证书失败: {str(e)}", exc_info=True)
        task.complete_failure(str(e))
        
        return {
            'success': False,
            'error': str(e)
        }
