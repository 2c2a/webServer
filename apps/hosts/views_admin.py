"""
主机管理 - 超管后台视图

所有视图均使用 @admin_required 装饰器保护。
超管可查看所有主机和主机组；提供商仅可查看自己创建或分配给自己的数据。
"""

import json
import logging
import os
import platform
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, TemplateView

from apps.accounts.provider_decorators import admin_required
from utils.provider import get_provider_hosts, PROVIDER_GROUP_NAME

from .forms_admin import AdminHostForm, AdminHostGroupForm
from .forms_wizard import HostWizardForm, CONNECTION_DEFAULT_PORTS, CONNECTION_DEFAULT_SSL
from .models import Host, HostGroup

User = get_user_model()
logger = logging.getLogger(__name__)


def _is_local_winserver():
    return platform.system() == 'Windows' and 'server' in platform.version().lower()


def _generate_init_command_data(request, host):
    from apps.bootstrap.models import InitialToken
    import base64

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)

    initial_token = InitialToken.objects.create(
        token=token,
        host=host,
        expires_at=expires_at,
        status='ISSUED',
    )

    pairing_code = initial_token.generate_pairing_code()

    config_data = {
        'c_side_url': request.build_absolute_uri(
            '/'
        ).rstrip('/'),
        'token': initial_token.token,
        'host_id': str(host.id),
        'expires_at': initial_token.expires_at.isoformat(),
    }
    config_json = json.dumps(config_data)
    encoded_config = base64.b64encode(
        config_json.encode('utf-8')
    ).decode('utf-8')

    one_liner = (
        "& ([ScriptBlock]::Create("
        "(irm https://static.2c2a.cc.cd/hostinitbash.ps1)"
        f")) -Secret '{encoded_config}'"
    )

    fallback_command = (
        "$e = \"$env:TEMP\\h_side_init.exe\"; "
        "irm https://2c2a.cc.cd/hostinitbash.exe "
        f"-OutFile $e; & $e '{encoded_config}'"
    )

    return {
        'pairing_code': pairing_code,
        'one_liner': one_liner,
        'fallback_command': fallback_command,
        'expires_at': initial_token.expires_at.isoformat(),
        'host_id': host.id,
        'hostname': host.hostname,
    }


def _get_host_form_context():
    return {
        'default_ports': json.dumps(CONNECTION_DEFAULT_PORTS),
        'default_ssl': json.dumps(CONNECTION_DEFAULT_SSL),
        'is_local_winserver': json.dumps(_is_local_winserver()),
    }


def _get_permission_context(form, host=None):
    provider_users = User.objects.filter(
        groups__name=PROVIDER_GROUP_NAME,
        is_staff=True,
        is_superuser=False,
    ).order_by('username')

    all_groups = Group.objects.all().order_by('name')

    provider_users_json = json.dumps([
        {'id': u.id, 'username': u.username}
        for u in provider_users
    ])
    groups_json = json.dumps([
        {
            'id': g.id,
            'name': g.name,
            'member_ids': list(
                g.user_set.filter(
                    groups__name=PROVIDER_GROUP_NAME,
                    is_staff=True,
                    is_superuser=False,
                )
                .values_list('id', flat=True)
                .distinct()
            ),
        }
        for g in all_groups
    ])

    provider_user_ids = list(provider_users.values_list('id', flat=True))

    initial_provider_ids = []

    if form.is_bound:
        initial_provider_ids = [
            int(x) for x in form.data.getlist('providers')
        ]
    elif host and host.pk:
        initial_provider_ids = list(
            host.providers.values_list('id', flat=True)
        )

    initial_permissions = []
    key_counter = 0
    for uid in initial_provider_ids:
        u = provider_users.filter(id=uid).first()
        if u:
            initial_permissions.append({
                'key': key_counter,
                'type': 'member',
                'targetId': u.id,
                'name': u.username,
                'userIds': [u.id],
            })
            key_counter += 1

    return {
        'provider_users': provider_users,
        'all_groups': all_groups,
        'provider_users_json': provider_users_json,
        'groups_json': groups_json,
        'provider_user_ids_json': json.dumps(provider_user_ids),
        'initial_permissions_json': json.dumps(initial_permissions),
        'initial_provider_ids_json': json.dumps(initial_provider_ids),
    }


# ========== 主机管理 ==========


@method_decorator(admin_required, name='dispatch')
class AdminHostListView(TemplateView):
    """
    超管主机列表视图

    显示所有主机，支持搜索和按连接类型/状态筛选。
    包含提供商列显示每个主机关联的提供商。
    """

    template_name = 'admin_base/hosts/host_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 数据隔离：超管查看所有主机，提供商仅查看自己的主机
        if self.request.user.is_superuser:
            hosts_qs = Host.objects.all().order_by('-created_at')
        else:
            hosts_qs = get_provider_hosts(self.request.user).order_by(
                '-created_at'
            )

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
        conn_filter = self.request.GET.get(
            'connection_type', ''
        ).strip()
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


@method_decorator(admin_required, name='dispatch')
class AdminHostDetailView(DetailView):
    """
    超管主机详情视图

    显示主机基本信息、提供商列表、管理员列表。
    """

    template_name = 'admin_base/hosts/host_detail.html'
    model = Host
    context_object_name = 'host'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        """超管可查看所有主机，提供商仅可查看自己的主机"""
        if self.request.user.is_superuser:
            return Host.objects.all()
        return get_provider_hosts(self.request.user)

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
            self.request.session.pop('generated_password', None)
            self.request.session.pop(
                'generated_password_host_id', None
            )

        context.update({
            'products': products,
            'user_count': user_count,
            'generated_password': generated_password,
            'page_title': f'主机 - {host.name}',
            'active_nav': 'hosts',
        })
        return context


@method_decorator(admin_required, name='dispatch')
class AdminHostCreateView(TemplateView):
    """
    超管主机创建视图

    处理 GET 和 POST 请求，创建新主机。
    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/hosts/host_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = kwargs.get('form', AdminHostForm())
        context.update({
            'form': form,
            'page_title': '添加主机',
            'active_nav': 'hosts',
            'is_create': True,
        })
        context.update(_get_permission_context(form))
        context.update(_get_host_form_context())
        return context

    def post(self, request, *args, **kwargs):
        form = AdminHostForm(
            request.POST, request.FILES
        )
        if form.is_valid():
            host = form.save(commit=False)
            host.created_by = request.user
            host.save()
            form.save_m2m()

            # 测试连接
            try:
                host.test_connection()
                status_display = dict(Host.STATUS_CHOICES).get(
                    host.status, host.status
                )
                messages.success(
                    request,
                    f'主机 {host.name} 创建成功，状态: '
                    f'{status_display}'
                )
            except Exception as e:
                messages.warning(
                    request,
                    f'主机 {host.name} 创建成功，'
                    f'但连接测试失败: {str(e)}'
                )

            # 如果自动生成了密码，提示用户
            if hasattr(form, 'generated_password') and \
                    form.generated_password:
                messages.info(
                    request,
                    f'已为主机 {host.name} 自动生成密码，'
                    f'请妥善保存。'
                )
                request.session['generated_password'] = (
                    form.generated_password
                )
                request.session['generated_password_host_id'] = (
                    host.pk
                )

            # 证书快速配置：用预生成的 token 创建 InitialToken
            init_token = request.POST.get('init_token')
            if (host.auth_method == 'certificate'
                    and init_token):
                try:
                    from apps.bootstrap.models import InitialToken
                    InitialToken.objects.filter(
                        token=init_token,
                    ).update(host=host)
                except Exception:
                    pass

            return redirect('admin:admin_hosts:host_detail', pk=host.pk)

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminHostUpdateView(TemplateView):
    """
    超管主机编辑视图

    处理 GET 和 POST 请求，编辑主机信息。
    密码字段可选，留空则不修改。
    """

    template_name = 'admin_base/hosts/host_form.html'

    def get_host(self):
        """获取当前编辑的主机，提供商仅可编辑自己的主机"""
        if self.request.user.is_superuser:
            return get_object_or_404(Host, pk=self.kwargs['pk'])
        return get_object_or_404(
            get_provider_hosts(self.request.user), pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        host = self.get_host()
        form = kwargs.get(
            'form', AdminHostForm(instance=host)
        )
        context.update({
            'form': form,
            'host': host,
            'page_title': f'编辑主机 - {host.name}',
            'active_nav': 'hosts',
            'is_create': False,
        })
        context.update(_get_permission_context(form, host))
        context.update(_get_host_form_context())
        return context

    def post(self, request, *args, **kwargs):
        host = self.get_host()
        form = AdminHostForm(
            request.POST, request.FILES, instance=host
        )
        if form.is_valid():
            host = form.save()

            # 如果密码被修改，测试连接
            if (
                'password' in form.changed_data
                and form.cleaned_data.get('password')
            ):
                try:
                    host.test_connection()
                    status_display = dict(
                        Host.STATUS_CHOICES
                    ).get(host.status, host.status)
                    messages.success(
                        request,
                        f'主机 {host.name} 更新成功，'
                        f'状态: {status_display}'
                    )
                except Exception as e:
                    messages.warning(
                        request,
                        f'主机 {host.name} 更新成功，'
                        f'但连接测试失败: {str(e)}'
                    )
            else:
                messages.success(
                    request, f'主机 {host.name} 更新成功'
                )

            return redirect(
                'admin:admin_hosts:host_detail', pk=host.pk
            )

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminHostDeleteView(TemplateView):
    """
    超管主机删除视图

    显示确认页面，处理删除请求。
    删除前清理关联的产品和公共主机信息。
    """

    template_name = 'admin_base/hosts/host_confirm_delete.html'

    def get_host(self):
        """获取当前删除的主机，提供商仅可删除自己的主机"""
        if self.request.user.is_superuser:
            return get_object_or_404(Host, pk=self.kwargs['pk'])
        return get_object_or_404(
            get_provider_hosts(self.request.user), pk=self.kwargs['pk']
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        host = self.get_host()

        # 获取关联信息用于确认页面
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
        PublicHostInfo.objects.filter(
            internal_host=host
        ).delete()

        host_name = host.name
        host.delete()

        messages.success(request, f'主机 {host_name} 已删除')
        return redirect('admin:admin_hosts:host_list')


@admin_required
def admin_host_test_connection(request, pk):
    """
    测试主机连接 AJAX 端点

    调用 Host.test_connection() 测试连接，
    返回 JSON 格式的测试结果。
    """
    if request.user.is_superuser:
        host = get_object_or_404(Host, pk=pk)
    else:
        host = get_object_or_404(
            get_provider_hosts(request.user), pk=pk
        )

    old_status = host.status
    error_message = None

    try:
        host.test_connection()
    except Exception as e:
        error_message = str(e)
        logger.error(
            f"测试主机连接异常: {host.name}, 错误: {error_message}"
        )

    host.refresh_from_db()
    new_status = host.status
    status_display = dict(Host.STATUS_CHOICES).get(
        new_status, new_status
    )

    success = new_status == 'online'

    result = {
        'success': success,
        'status': new_status,
        'status_display': status_display,
        'old_status': old_status,
    }

    if error_message:
        result['error'] = error_message

    if success:
        result['message'] = f'连接成功，主机状态: {status_display}'
    elif new_status == 'error':
        result['message'] = (
            f'连接失败，主机状态: {status_display}'
        )
        if error_message:
            result['message'] += f'（{error_message}）'
    else:
        result['message'] = f'主机状态: {status_display}'

    return JsonResponse(result)


# ========== 主机组管理 ==========


@method_decorator(admin_required, name='dispatch')
class AdminHostGroupListView(TemplateView):
    """
    超管主机组列表视图

    显示所有主机组，支持搜索。
    包含提供商列和主机数量。
    """

    template_name = 'admin_base/hosts/hostgroup_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 数据隔离：超管查看所有主机组，提供商仅查看自己创建的
        if self.request.user.is_superuser:
            hostgroups_qs = HostGroup.objects.all().order_by(
                '-created_at'
            )
        else:
            hostgroups_qs = HostGroup.objects.filter(
                created_by=self.request.user
            ).order_by('-created_at')

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


@method_decorator(admin_required, name='dispatch')
class AdminHostGroupCreateView(TemplateView):
    """
    超管主机组创建视图

    处理 GET 和 POST 请求，创建新主机组。
    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/hosts/hostgroup_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get(
                'form', AdminHostGroupForm()
            ),
            'page_title': '创建主机组',
            'active_nav': 'hosts',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = AdminHostGroupForm(request.POST)
        if form.is_valid():
            hostgroup = form.save(commit=False)
            hostgroup.created_by = request.user
            hostgroup.save()
            form.save_m2m()

            messages.success(
                request,
                f'主机组 {hostgroup.name} 创建成功'
            )
            return redirect('admin:admin_hosts:hostgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminHostGroupUpdateView(TemplateView):
    """
    超管主机组编辑视图

    处理 GET 和 POST 请求，编辑主机组信息。
    """

    template_name = 'admin_base/hosts/hostgroup_form.html'

    def get_hostgroup(self):
        """获取当前编辑的主机组，提供商仅可编辑自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(HostGroup, pk=self.kwargs['pk'])
        return get_object_or_404(
            HostGroup, pk=self.kwargs['pk'],
            created_by=self.request.user,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        hostgroup = self.get_hostgroup()
        form = kwargs.get(
            'form',
            AdminHostGroupForm(instance=hostgroup)
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
        form = AdminHostGroupForm(
            request.POST, instance=hostgroup
        )
        if form.is_valid():
            hostgroup = form.save()
            messages.success(
                request,
                f'主机组 {hostgroup.name} 更新成功'
            )
            return redirect('admin:admin_hosts:hostgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminHostGroupDeleteView(TemplateView):
    """
    超管主机组删除视图

    显示确认页面，处理删除请求。
    """

    template_name = (
        'admin_base/hosts/hostgroup_confirm_delete.html'
    )

    def get_hostgroup(self):
        """获取当前删除的主机组，提供商仅可删除自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(HostGroup, pk=self.kwargs['pk'])
        return get_object_or_404(
            HostGroup, pk=self.kwargs['pk'],
            created_by=self.request.user,
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
        return redirect('admin:admin_hosts:hostgroup_list')


# ========== 主机创建向导 ==========


@admin_required
def admin_host_wizard(request):
    """
    主机创建向导视图

    引导超管分步添加主机：
    - Step 1: 基本信息 (名称、地址、连接类型)
    - Step 2: 连接配置 (端口、SSL、认证)
    - Step 3: 分配提供商 (提供商、描述)

    使用 Alpine.js 在客户端管理步骤切换，
    最终一次性提交表单创建主机。
    """
    if request.method == 'POST':
        form = HostWizardForm(
            request.POST, request.FILES
        )
        if form.is_valid():
            host = form.save(commit=False)
            host.created_by = request.user
            host.save()
            form.save_m2m()

            # 测试连接
            try:
                host.test_connection()
                status_display = dict(Host.STATUS_CHOICES).get(
                    host.status, host.status
                )
                messages.success(
                    request,
                    f'主机 {host.name} 创建成功，'
                    f'状态: {status_display}'
                )
            except Exception as e:
                messages.warning(
                    request,
                    f'主机 {host.name} 创建成功，'
                    f'但连接测试失败: {str(e)}'
                )

            # 如果自动生成了密码，提示用户
            if hasattr(form, 'generated_password') and \
                    form.generated_password:
                messages.info(
                    request,
                    f'已为主机 {host.name} 自动生成密码，'
                    f'请妥善保存。'
                )
                # 将生成的密码存入 session 以便在详情页展示
                request.session['generated_password'] = (
                    form.generated_password
                )
                request.session['generated_password_host_id'] = (
                    host.pk
                )

            return redirect('admin:admin_hosts:host_detail', pk=host.pk)
    else:
        form = HostWizardForm()

    # 获取提供商列表及主机数量（用于向导第三步）
    providers_with_count = form.get_providers_with_host_count()

    gateway_url = os.environ.get(
        'TUNNEL_GATEWAY_URL',
        'wss://gateway.2c2a.com:9000'
    )
    server_base_url = os.environ.get(
        'TUNNEL_SERVER_BASE_URL',
        request.build_absolute_uri('/').rstrip('/')
    )

    context = {
        'form': form,
        'providers_with_count': providers_with_count,
        'connection_type_choices': [
            c for c in Host.CONNECTION_TYPE_CHOICES
            if c[0] in ('winrm', 'localwinserver')
        ],
        'os_type_choices': Host.OS_TYPE_CHOICES,
        'auth_method_choices': Host.AUTH_METHOD_CHOICES,
        'default_ports': json.dumps(CONNECTION_DEFAULT_PORTS),
        'default_ssl': json.dumps(CONNECTION_DEFAULT_SSL),
        'is_local_winserver': json.dumps(_is_local_winserver()),
        'gateway_url': gateway_url,
        'server_base_url': server_base_url,
        'page_title': '添加主机',
        'active_nav': 'hosts',
    }

    return render(
        request,
        'admin_base/hosts/host_wizard.html',
        context,
    )


@admin_required
def admin_host_wizard_generate_init_command(request):
    if request.method != 'POST':
        return JsonResponse(
            {'success': False, 'error': 'Method not allowed'},
            status=405,
        )

    import base64
    from apps.bootstrap.models import InitialToken

    InitialToken.objects.filter(
        host=None,
        status='ISSUED',
    ).delete()

    token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)

    InitialToken.objects.create(
        token=token,
        host=None,
        expires_at=expires_at,
        status='ISSUED',
    )

    c_side_url = request.build_absolute_uri('/').rstrip('/')
    config_data = {
        'c_side_url': c_side_url,
        'token': token,
    }
    config_json = json.dumps(config_data)
    encoded_config = base64.b64encode(
        config_json.encode('utf-8')
    ).decode('utf-8')

    one_liner = (
        "& ([ScriptBlock]::Create("
        "(irm https://2c2a.cc.cd/hostinitbash.ps1)"
        f")) -Secret '{encoded_config}'"
    )

    fallback_command = (
        "$e = \"$env:TEMP\\h_side_init.exe\"; "
        "irm https://2c2a.cc.cd/hostinitbash.exe "
        f"-OutFile $e; & $e '{encoded_config}'"
    )

    return JsonResponse({
        'success': True,
        'data': {
            'token': token,
            'one_liner': one_liner,
            'fallback_command': fallback_command,
        },
    })


@admin_required
def admin_host_wizard_generate_token(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        token = secrets.token_urlsafe(32)
        gateway_url = os.environ.get(
            'TUNNEL_GATEWAY_URL',
            'wss://gateway.2c2a.com:9000'
        )
        server_base_url = os.environ.get(
            'TUNNEL_SERVER_BASE_URL',
            request.build_absolute_uri('/').rstrip('/')
        )

        return JsonResponse({
            'success': True,
            'tunnel_token': token,
            'gateway_url': gateway_url,
            'server_base_url': server_base_url,
        })
    except Exception as e:
        logger.error(f"Error generating tunnel token: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': 'Failed to generate tunnel token',
        }, status=500)


@admin_required
def admin_host_wizard_test_connection(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'success': False, 'error': '请求数据格式无效'}, status=400)

    connection_type = data.get('connection_type', 'winrm')
    hostname = data.get('hostname', '').strip()
    port = data.get('port', 5985)
    use_ssl = data.get('use_ssl', False)
    auth_method = data.get('auth_method', 'ntlm')
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not hostname:
        return JsonResponse({'success': False, 'error': '主机地址不能为空'}, status=400)

    if auth_method == 'ntlm':
        if not username:
            return JsonResponse({'success': False, 'error': '用户名不能为空'}, status=400)
        if not password:
            return JsonResponse({'success': False, 'error': '密码不能为空'}, status=400)

    try:
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
        elif connection_type == 'winrm' and auth_method == 'certificate':
            return JsonResponse({
                'success': False,
                'error': '证书认证方式请先保存主机后再测试连接',
            })
        else:
            return JsonResponse({
                'success': False,
                'error': f'不支持的连接类型: {connection_type}',
            })

        if result.success:
            output = result.std_out.strip() if result.std_out else ''
            return JsonResponse({
                'success': True,
                'message': f'连接成功{f" ({output})" if output else ""}',
            })
        else:
            error_detail = result.std_err.strip() if result.std_err else f'命令执行返回非零状态码: {result.status_code}'
            return JsonResponse({
                'success': False,
                'error': f'连接失败: {error_detail}',
            })

    except Exception as e:
        error_message = str(e)
        logger.error(f"向导即时连接测试失败: {hostname}, 错误: {error_message}")
        return JsonResponse({
            'success': False,
            'error': f'连接测试失败: {error_message}',
        })


@admin_required
def admin_host_generate_init_command(request, pk):
    host = get_object_or_404(Host, pk=pk)

    if request.method != 'POST':
        return JsonResponse(
            {'success': False, 'error': 'Method not allowed'},
            status=405,
        )

    try:
        init_data = _generate_init_command_data(request, host)
        return JsonResponse({'success': True, 'data': init_data})
    except Exception as e:
        return JsonResponse(
            {'success': False, 'error': str(e)},
            status=500,
        )
