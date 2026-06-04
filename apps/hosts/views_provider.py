"""
主机管理 - 提供商后台视图

所有视图均使用 @provider_required 装饰器保护，确保只有提供商用户可以访问。
数据隔离通过 utils.provider 中的 get_provider_hosts 函数实现。
"""

import base64
import json
import logging
import secrets

from datetime import timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, TemplateView

from apps.accounts.provider_decorators import provider_required
from apps.provider.context_mixin import ProviderContextMixin
from utils.provider import get_provider_hosts

from .forms_provider import HostCreateForm, HostUpdateForm, HostGroupForm
from .models import Host, HostGroup

logger = logging.getLogger(__name__)


@method_decorator(provider_required, name='dispatch')
class HostListView(ProviderContextMixin, TemplateView):
    """
    主机列表视图

    提供分页、搜索和筛选功能，仅显示当前提供商可见的主机。
    """

    template_name = 'admin_base/hosts/host_list.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # 获取提供商可见的主机
        hosts_qs = get_provider_hosts(user, site_group=getattr(self.request, 'site_group', None)).order_by('-created_at')

        # 搜索过滤
        search = self.request.GET.get('search', '').strip()
        if search:
            hosts_qs = hosts_qs.filter(
                Q(name__icontains=search)
                | Q(hostname__icontains=search)
                | Q(username__icontains=search)
            )

        # 状态过滤
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter:
            hosts_qs = hosts_qs.filter(status=status_filter)

        # 连接类型过滤
        conn_filter = self.request.GET.get('connection_type', '').strip()
        if conn_filter:
            hosts_qs = hosts_qs.filter(connection_type=conn_filter)

        # 分页
        paginator = Paginator(hosts_qs, 15)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'hosts': page_obj,
            'search': search,
            'status_filter': status_filter,
            'connection_type_filter': conn_filter,
            'status_choices': Host.STATUS_CHOICES,
            'connection_type_choices': Host.CONNECTION_TYPE_CHOICES,
            'page_title': '主机管理',
            'active_nav': 'hosts',
        })
        return context


@method_decorator(provider_required, name='dispatch')
class HostDetailView(ProviderContextMixin, DetailView):
    """
    主机详情视图

    显示主机基本信息、隧道状态、关联产品等。
    """

    template_name = 'admin_base/hosts/host_detail.html'
    model = Host
    context_object_name = 'host'
    pk_url_kwarg = 'pk'
    provider_url_namespace = 'provider:provider_hosts'

    def get_queryset(self):
        """确保提供商只能查看自己的主机"""
        return get_provider_hosts(self.request.user, site_group=getattr(self.request, 'site_group', None))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        host = self.object

        # 获取关联产品
        from apps.operations.models import Product
        products = Product.objects.filter(host=host)

        # 获取关联用户数
        from apps.operations.models import CloudComputerUser
        user_count = CloudComputerUser.objects.filter(
            product__in=products
        ).count()

        # 检查 session 中是否有生成的密码
        generated_password = None
        if (
            self.request.session.get('generated_password_host_id')
            == host.pk
        ):
            generated_password = self.request.session.get(
                'generated_password'
            )
            # 一次性读取后清除
            self.request.session.pop('generated_password', None)
            self.request.session.pop('generated_password_host_id', None)

        context.update({
            'products': products,
            'user_count': user_count,
            'generated_password': generated_password,
            'page_title': f'主机 - {host.name}',
            'active_nav': 'hosts',
        })
        return context


@method_decorator(provider_required, name='dispatch')
class HostCreateView(ProviderContextMixin, TemplateView):
    """
    主机创建视图

    处理 GET 和 POST 请求，创建新主机。
    自动设置 created_by 为当前用户，并将用户添加到 administrators。
    """

    template_name = 'admin_base/hosts/host_form.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get('form', HostCreateForm()),
            'page_title': '添加主机',
            'active_nav': 'hosts',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = HostCreateForm(request.POST)
        if form.is_valid():
            host = form.save(commit=False)
            host.created_by = request.user
            host.save()
            # 将创建者添加到管理员列表
            host.administrators.add(request.user)

            # 测试连接（异步）
            from apps.hosts.tasks import test_winrm_connection
            test_winrm_connection.delay(host.pk)
            messages.success(
                request,
                f'主机 {host.name} 创建成功，'
                f'连接测试正在后台执行'
            )

            # 如果自动生成了密码，提示用户
            if form.generated_password:
                messages.info(
                    request,
                    f'已为主机 {host.name} 自动生成密码，请妥善保存。'
                )
                # 将生成的密码存入 session 以便在详情页展示
                request.session['generated_password'] = (
                    form.generated_password
                )
                request.session['generated_password_host_id'] = host.pk

            return redirect(
                'provider:provider_hosts:host_detail', pk=host.pk
            )

        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(provider_required, name='dispatch')
class HostUpdateView(ProviderContextMixin, TemplateView):
    """
    主机编辑视图

    处理 GET 和 POST 请求，编辑主机信息。
    密码字段可选，留空则不修改。
    """

    template_name = 'admin_base/hosts/host_form.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_host(self):
        return get_object_or_404(
            get_provider_hosts(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        host = self.get_host()
        form = kwargs.get('form', HostUpdateForm(instance=host))
        context.update({
            'form': form,
            'host': host,
            'page_title': f'编辑主机 - {host.name}',
            'active_nav': 'hosts',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        host = self.get_host()
        form = HostUpdateForm(request.POST, instance=host)
        if form.is_valid():
            host = form.save()

            # 如果密码被修改，异步测试连接
            if (
                'password' in form.changed_data
                and form.cleaned_data.get('password')
            ):
                from apps.hosts.tasks import test_winrm_connection
                test_winrm_connection.delay(host.pk)
                messages.success(
                    request,
                    f'主机 {host.name} 更新成功，'
                    f'连接测试正在后台执行'
                )
            else:
                messages.success(
                    request, f'主机 {host.name} 更新成功'
                )

            return redirect(
                'provider:provider_hosts:host_detail', pk=host.pk
            )

        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(provider_required, name='dispatch')
class HostDeleteView(ProviderContextMixin, TemplateView):
    """
    主机删除视图

    显示确认页面，处理删除请求。
    删除前清理关联的产品和公共主机信息。
    """

    template_name = 'admin_base/hosts/host_confirm_delete.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_host(self):
        return get_object_or_404(
            get_provider_hosts(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        host = self.get_host()

        from apps.operations.models import Product
        products = Product.objects.filter(host=host)

        context.update({
            'host': host,
            'product_count': products.count(),
            'page_title': f'删除主机 - {host.name}',
            'active_nav': 'hosts',
        })
        return context

    def post(self, request, *args, **kwargs):
        host = self.get_host()

        # 删除关联的产品和公共主机信息
        from apps.operations.models import Product, PublicHostInfo
        Product.objects.filter(host=host).delete()
        PublicHostInfo.objects.filter(internal_host=host).delete()

        host_name = host.name
        host.delete()

        messages.success(request, f'主机 {host_name} 已删除')
        return redirect('provider:provider_hosts:host_list')


@method_decorator(provider_required, name='dispatch')
class HostDeployCommandView(View):
    """
    生成部署命令视图

    为主机生成部署命令，复用 Admin 中的部署命令生成逻辑。
    返回 JSON 响应，供前端 AJAX 调用。
    """

    def get_host(self):
        return get_object_or_404(
            get_provider_hosts(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def get(self, request, *args, **kwargs):
        host = self.get_host()
        try:
            from apps.bootstrap.models import InitialToken

            current_time = timezone.now()
            valid_tokens = InitialToken.objects.filter(
                host=host,
                status__in=['ISSUED', 'PAIRED'],
                expires_at__gt=current_time
            ).order_by('-created_at')

            if valid_tokens.exists():
                existing_token = valid_tokens.first()
                initial_token = existing_token
                created = False
                token_message = '复用现有引导令牌'
                pairing_code = initial_token.generate_pairing_code()
            else:
                token = secrets.token_urlsafe(32)
                expires_at = current_time + timedelta(hours=24)

                initial_token, created = (
                    InitialToken.objects.get_or_create(
                        token=token,
                        defaults={
                            'host': host,
                            'expires_at': expires_at,
                            'status': 'ISSUED'
                        }
                    )
                )
                token_message = '新引导令牌已生成'
                pairing_code = initial_token.generate_pairing_code()

            current_site = request.build_absolute_uri('/')

            secret_data = {
                'c_side_url': current_site.rstrip('/'),
                'token': initial_token.token,
                'host_id': str(host.id),
                'hostname': host.hostname,
                'generated_at': current_time.isoformat(),
                'expires_at': initial_token.expires_at.isoformat()
            }

            json_str = json.dumps(secret_data, ensure_ascii=False)
            encoded_bytes = base64.b64encode(json_str.encode('utf-8'))
            encoded_str = encoded_bytes.decode('utf-8')

            deploy_command = (
                f'.\\h_side_init.exe "{encoded_str}"'
            )

            return JsonResponse({
                'success': True,
                'deploy_command': deploy_command,
                'secret': encoded_str,
                'pairing_code': pairing_code,
                'pairing_code_expiry': (
                    initial_token.pairing_code_expires_at.isoformat()
                    if initial_token.pairing_code_expires_at else None
                ),
                'expires_at': initial_token.expires_at.isoformat(),
                'message': f'{token_message}，将在24小时后过期',
                'token_id': initial_token.token,
                'token_status': initial_token.status,
                'created_new': created
            })

        except Exception as e:
            logger.error(
                f'生成部署命令时发生错误: {str(e)}', exc_info=True
            )
            return JsonResponse({
                'success': False,
                'error': '生成部署命令失败'
            }, status=500)


@method_decorator(provider_required, name='dispatch')
class HostToggleActiveView(View):
    """
    切换主机活跃状态视图

    AJAX 端点，用于快速切换主机的在线/离线状态。
    """

    def get_host(self):
        return get_object_or_404(
            get_provider_hosts(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def post(self, request, *args, **kwargs):
        host = self.get_host()

        if host.status == 'online':
            new_status = 'offline'
            Host.objects.filter(pk=host.pk).update(status=new_status)
        else:
            from apps.hosts.tasks import test_winrm_connection
            test_winrm_connection.delay(host.pk)
            new_status = 'pending'

        status_display = dict(Host.STATUS_CHOICES).get(
            new_status, new_status
        )
        return JsonResponse({
            'success': True,
            'status': new_status,
            'status_display': status_display,
        })


# ========== 主机组管理 ==========


def get_provider_hostgroups(user, site_group=None):
    qs = HostGroup.objects.filter(
        Q(created_by=user) | Q(providers=user)
    ).distinct()
    if site_group is not None:
        qs = qs.filter(site_group=site_group)
    return qs


@method_decorator(provider_required, name='dispatch')
class HostGroupListView(ProviderContextMixin, TemplateView):
    """
    主机组列表视图

    提供分页和搜索功能，仅显示当前提供商可见的主机组。
    """

    template_name = 'admin_base/hosts/hostgroup_list.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        # 获取提供商可见的主机组
        hostgroups_qs = get_provider_hostgroups(user, site_group=getattr(self.request, 'site_group', None)).order_by(
            '-created_at'
        )

        # 搜索过滤
        search = self.request.GET.get('search', '').strip()
        if search:
            hostgroups_qs = hostgroups_qs.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        # 分页
        paginator = Paginator(hostgroups_qs, 15)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'hostgroups': page_obj,
            'search': search,
            'page_title': '主机组管理',
            'active_nav': 'hosts',
        })
        return context


@method_decorator(provider_required, name='dispatch')
class HostGroupCreateView(ProviderContextMixin, TemplateView):
    """
    主机组创建视图

    处理 GET 和 POST 请求，创建新主机组。
    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/hosts/hostgroup_form.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get(
                'form',
                HostGroupForm(provider_user=self.request.user)
            ),
            'page_title': '创建主机组',
            'active_nav': 'hosts',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = HostGroupForm(
            request.POST, provider_user=request.user
        )
        if form.is_valid():
            hostgroup = form.save(commit=False)
            hostgroup.created_by = request.user
            hostgroup.save()
            form.save_m2m()

            messages.success(
                request,
                f'主机组 {hostgroup.name} 创建成功'
            )
            return redirect(
                'provider:provider_hosts:hostgroup_list'
            )

        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(provider_required, name='dispatch')
class HostGroupUpdateView(ProviderContextMixin, TemplateView):
    """
    主机组编辑视图

    处理 GET 和 POST 请求，编辑主机组信息。
    """

    template_name = 'admin_base/hosts/hostgroup_form.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_hostgroup(self):
        return get_object_or_404(
            get_provider_hostgroups(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hostgroup = self.get_hostgroup()
        form = kwargs.get(
            'form',
            HostGroupForm(
                instance=hostgroup,
                provider_user=self.request.user
            )
        )
        context.update({
            'form': form,
            'hostgroup': hostgroup,
            'page_title': f'编辑主机组 - {hostgroup.name}',
            'active_nav': 'hosts',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        hostgroup = self.get_hostgroup()
        form = HostGroupForm(
            request.POST,
            instance=hostgroup,
            provider_user=request.user
        )
        if form.is_valid():
            hostgroup = form.save()
            messages.success(
                request,
                f'主机组 {hostgroup.name} 更新成功'
            )
            return redirect(
                'provider:provider_hosts:hostgroup_list'
            )

        return self.render_to_response(self.get_context_data(form=form))


@method_decorator(provider_required, name='dispatch')
class HostGroupDeleteView(ProviderContextMixin, TemplateView):
    """
    主机组删除视图

    显示确认页面，处理删除请求。
    """

    template_name = 'admin_base/hosts/hostgroup_confirm_delete.html'
    provider_url_namespace = 'provider:provider_hosts'

    def get_hostgroup(self):
        return get_object_or_404(
            get_provider_hostgroups(self.request.user, site_group=getattr(self.request, 'site_group', None)),
            pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hostgroup = self.get_hostgroup()

        context.update({
            'hostgroup': hostgroup,
            'host_count': hostgroup.hosts.count(),
            'page_title': f'删除主机组 - {hostgroup.name}',
            'active_nav': 'hosts',
        })
        return context

    def post(self, request, *args, **kwargs):
        hostgroup = self.get_hostgroup()
        hostgroup_name = hostgroup.name
        hostgroup.delete()

        messages.success(
            request,
            f'主机组 {hostgroup_name} 已删除'
        )
        return redirect('provider:provider_hosts:hostgroup_list')
