"""
运营管理 - 提供商后台视图

包含开户申请、云电脑用户、邀请令牌、访问授权、RDP域名路由、系统任务、
产品管理、产品组管理等视图。
所有视图均受提供商身份验证保护，并实施提供商数据隔离。
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.operations.models import (
    AccountOpeningRequest,
    CloudComputerUser,
    Product,
    ProductGroup,
    ProductInvitationToken,
    ProductAccessGrant,
    RdpDomainRoute,
    SystemTask,
)
from apps.provider.decorators import is_provider, provider_required
from apps.provider.context_mixin import ProviderContextMixin
from utils.provider import get_provider_products

from .forms_provider import (
    AccountOpeningRequestRejectForm,
    CloudComputerUserDiskQuotaForm,
    CloudComputerUserResetPasswordForm,
    ProductForm,
    ProductGroupForm,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ========== 基础混入类 ==========


class ProviderOperationBaseView(View):
    """
    提供商运营管理基础视图混入类

    - 验证提供商身份
    - 提供数据隔离的查询集
    """

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_provider(request.user):
            return redirect('accounts:login')
        return super().dispatch(request, *args, **kwargs)

    def get_provider_queryset(self):
        """
        获取提供商可见的云电脑用户查询集
        提供商只能看到自己产品下的用户
        """
        return CloudComputerUser.objects.filter(
            product__created_by=self.request.user
        ).select_related(
            'product',
            'product__host',
            'created_from_request',
            'created_from_request__applicant',
        )

    def get_provider_products(self):
        """获取提供商创建的产品"""
        return Product.objects.filter(created_by=self.request.user)


# ========== 用户列表视图 ==========


class CloudComputerUserListView(ProviderContextMixin, ProviderOperationBaseView, TemplateView):
    """
    云电脑用户列表视图

    支持搜索、状态筛选、分页、批量操作
    """
    template_name = 'admin_base/operations/user_list.html'
    paginate_by = 20
    provider_url_namespace = 'provider:provider_operations'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        queryset = self.get_provider_queryset()

        # 搜索过滤
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                username__icontains=search
            ) | queryset.filter(
                fullname__icontains=search
            ) | queryset.filter(
                email__icontains=search
            ) | queryset.filter(
                product__display_name__icontains=search
            )
            # 去重
            queryset = queryset.distinct()

        # 状态过滤
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # 产品过滤
        product_filter = self.request.GET.get('product', '').strip()
        if product_filter:
            queryset = queryset.filter(product_id=product_filter)

        # 排序
        queryset = queryset.order_by('-created_at')

        # 分页
        paginator = Paginator(queryset, self.paginate_by)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 状态选项
        status_choices = CloudComputerUser._meta.get_field('status').choices

        context.update({
            'page_obj': page_obj,
            'users': page_obj,
            'search': search,
            'status_filter': status_filter,
            'product_filter': product_filter,
            'status_choices': status_choices,
            'products': self.get_provider_products(),
            'page_title': '云电脑用户',
            'active_nav': 'cloud_users',
        })

        return context


# ========== 用户详情视图 ==========


class CloudComputerUserDetailView(ProviderContextMixin, ProviderOperationBaseView, DetailView):
    """
    云电脑用户详情视图

    显示用户信息、管理员状态、磁盘配额等
    """
    template_name = 'admin_base/operations/user_detail.html'
    context_object_name = 'cloud_user'
    pk_url_kwarg = 'pk'
    provider_url_namespace = 'provider:provider_operations'

    def get_queryset(self):
        return self.get_provider_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cloud_user = self.object

        context.update({
            'page_title': f'用户详情 - {cloud_user.username}',
            'active_nav': 'cloud_users',
            'disk_quota_json': json.dumps(cloud_user.disk_quota, ensure_ascii=False) if cloud_user.disk_quota else '{}',
        })

        return context


# ========== 同步管理员状态视图 ==========


class CloudComputerUserSyncAdminView(ProviderOperationBaseView, View):
    """
    同步管理员状态视图

    POST 请求：切换用户的管理员权限（授予/撤销）
    """

    def get_queryset(self):
        return self.get_provider_queryset()

    def post(self, request, pk):
        cloud_user = get_object_or_404(self.get_queryset(), pk=pk)

        try:
            from .services import update_user_admin_permission

            new_is_admin = not cloud_user.is_admin
            update_user_admin_permission(cloud_user, new_is_admin)

            # 更新数据库
            cloud_user.is_admin = new_is_admin
            cloud_user.save(update_fields=['is_admin', 'updated_at'])

            action = '授予' if new_is_admin else '撤销'
            messages.success(
                request,
                f'成功{action}用户 {cloud_user.username} 的管理员权限'
            )
        except Exception as e:
            action = '授予' if not cloud_user.is_admin else '撤销'
            messages.error(
                request,
                f'{action}用户 {cloud_user.username} 的管理员权限失败: {str(e)}'
            )

        return HttpResponseRedirect(
            reverse('provider_operations:user_detail', kwargs={'pk': pk})
        )


# ========== 设置磁盘配额视图 ==========


class CloudComputerUserSetDiskQuotaView(ProviderContextMixin, ProviderOperationBaseView, View):
    """
    设置磁盘配额视图

    GET 请求：显示配额设置表单
    POST 请求：提交配额设置并远程执行
    """
    provider_url_namespace = 'provider:provider_operations'

    def get_queryset(self):
        return self.get_provider_queryset()

    def get(self, request, pk):
        cloud_user = get_object_or_404(self.get_queryset(), pk=pk)
        initial_data = {
            'disk_quota': json.dumps(cloud_user.disk_quota, ensure_ascii=False, indent=2) if cloud_user.disk_quota else '{}',
        }
        form = CloudComputerUserDiskQuotaForm(initial=initial_data)

        return render(request, 'admin_base/operations/user_disk_quota.html', {
            'form': form,
            'cloud_user': cloud_user,
            'page_title': f'设置磁盘配额 - {cloud_user.username}',
            'active_nav': 'cloud_users',
        })

    def post(self, request, pk):
        cloud_user = get_object_or_404(self.get_queryset(), pk=pk)
        form = CloudComputerUserDiskQuotaForm(request.POST)

        if form.is_valid():
            disk_quota = form.cleaned_data['disk_quota']

            try:
                # 更新数据库
                cloud_user.disk_quota = disk_quota
                cloud_user.save(update_fields=['disk_quota', 'updated_at'])

                # 远程设置磁盘配额
                if disk_quota and cloud_user.product.enable_disk_quota:
                    from apps.operations.tasks import remote_set_user_disk_quotas
                    remote_set_user_disk_quotas.delay(
                        cloud_user.pk, disk_quota,
                        operator_id=request.user.pk,
                    )
                    messages.success(
                        request,
                        f'已保存用户 {cloud_user.username} 的磁盘配额配置，'
                        f'远程设置正在后台执行'
                    )
                else:
                    messages.success(
                        request,
                        f'已保存用户 {cloud_user.username} 的磁盘配额配置'
                    )

                return HttpResponseRedirect(
                    reverse('provider_operations:user_detail', kwargs={'pk': pk})
                )

            except Exception as e:
                messages.error(
                    request,
                    f'设置用户 {cloud_user.username} 磁盘配额失败: {str(e)}'
                )
        else:
            messages.error(request, '表单数据无效，请检查后重试')

        return render(request, 'admin_base/operations/user_disk_quota.html', {
            'form': form,
            'cloud_user': cloud_user,
            'page_title': f'设置磁盘配额 - {cloud_user.username}',
            'active_nav': 'cloud_users',
        })


# ========== 重置密码视图 ==========


class CloudComputerUserResetPasswordView(ProviderContextMixin, ProviderOperationBaseView, View):
    """
    重置密码视图

    GET 请求：显示密码重置表单
    POST 请求：提交新密码并远程执行
    """
    provider_url_namespace = 'provider:provider_operations'

    def get_queryset(self):
        return self.get_provider_queryset()

    def get(self, request, pk):
        cloud_user = get_object_or_404(self.get_queryset(), pk=pk)
        form = CloudComputerUserResetPasswordForm()

        return render(request, 'admin_base/operations/user_reset_password.html', {
            'form': form,
            'cloud_user': cloud_user,
            'page_title': f'重置密码 - {cloud_user.username}',
            'active_nav': 'cloud_users',
        })

    def post(self, request, pk):
        cloud_user = get_object_or_404(self.get_queryset(), pk=pk)
        form = CloudComputerUserResetPasswordForm(request.POST)

        if form.is_valid():
            new_password = form.cleaned_data['new_password']

            try:
                cloud_user.reset_windows_password(new_password)
                messages.success(
                    request,
                    f'成功重置用户 {cloud_user.username} 的密码'
                )
                return HttpResponseRedirect(
                    reverse('provider_operations:user_detail', kwargs={'pk': pk})
                )
            except Exception as e:
                messages.error(
                    request,
                    f'重置用户 {cloud_user.username} 的密码失败: {str(e)}'
                )
        else:
            messages.error(request, '表单数据无效，请检查后重试')

        return render(request, 'admin_base/operations/user_reset_password.html', {
            'form': form,
            'cloud_user': cloud_user,
            'page_title': f'重置密码 - {cloud_user.username}',
            'active_nav': 'cloud_users',
        })


# ========== 批量操作视图 ==========


class CloudComputerUserBatchActivateView(ProviderOperationBaseView, View):
    """
    批量激活用户视图

    POST 请求：批量激活选中的用户
    """

    def post(self, request):
        user_ids = request.POST.getlist('selected_ids')

        if not user_ids:
            messages.warning(request, '未选择任何用户')
            return HttpResponseRedirect(reverse('provider_operations:user_list'))

        queryset = self.get_provider_queryset().filter(
            pk__in=user_ids,
            status__in=['inactive', 'disabled'],
        )

        updated_count = queryset.update(status='active')

        if updated_count > 0:
            messages.success(request, f'成功激活了 {updated_count} 个用户')
        else:
            messages.warning(request, '没有符合条件的用户需要激活')

        return HttpResponseRedirect(reverse('provider_operations:user_list'))


class CloudComputerUserBatchDeactivateView(ProviderOperationBaseView, View):
    """
    批量停用用户视图

    POST 请求：批量停用选中的用户
    """

    def post(self, request):
        user_ids = request.POST.getlist('selected_ids')

        if not user_ids:
            messages.warning(request, '未选择任何用户')
            return HttpResponseRedirect(reverse('provider_operations:user_list'))

        queryset = self.get_provider_queryset().filter(
            pk__in=user_ids,
            status='active',
        )

        updated_count = queryset.update(status='inactive')

        if updated_count > 0:
            messages.success(request, f'成功停用了 {updated_count} 个用户')
        else:
            messages.warning(request, '没有符合条件的用户需要停用')

        return HttpResponseRedirect(reverse('provider_operations:user_list'))


class CloudComputerUserBatchDisableView(ProviderOperationBaseView, View):
    """
    批量禁用用户视图

    POST 请求：批量禁用选中的用户
    """

    def post(self, request):
        user_ids = request.POST.getlist('selected_ids')

        if not user_ids:
            messages.warning(request, '未选择任何用户')
            return HttpResponseRedirect(reverse('provider_operations:user_list'))

        queryset = self.get_provider_queryset().filter(
            pk__in=user_ids,
        ).exclude(status='deleted')

        updated_count = queryset.update(status='disabled')

        if updated_count > 0:
            messages.success(request, f'成功禁用了 {updated_count} 个用户')
        else:
            messages.warning(request, '没有符合条件的用户需要禁用')

        return HttpResponseRedirect(reverse('provider_operations:user_list'))


# ===========================================================================
# 共享辅助函数
# ===========================================================================


def _get_selected_ids(request):
    """
    从 POST 请求中提取选中的 ID 列表

    支持两种格式：
    1. 表单字段: selected_ids=1&selected_ids=2
    2. JSON 字符串: selected_ids=[1,2,3]
    """
    ids = request.POST.getlist('selected_ids')
    if ids:
        return [int(i) for i in ids if i.strip().isdigit()]

    raw = request.POST.get('selected_ids', '')
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [
                    int(i) for i in parsed
                    if isinstance(i, (int, str))
                    and str(i).isdigit()
                ]
        except (json.JSONDecodeError, ValueError):
            pass

    return []


# ===========================================================================
# 开户申请管理
# ===========================================================================


class ProviderRequestMixin(ProviderContextMixin):
    """
    提供商开户申请数据隔离 Mixin

    - dispatch: 验证提供商身份
    - get_queryset: 限制为当前提供商产品下的申请
    """

    provider_url_namespace = 'provider:provider_operations'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_provider(request.user):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden(
                '您没有提供商权限，无法访问此页面。'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_provider_queryset(self):
        """获取当前提供商可见的开户申请查询集"""
        return AccountOpeningRequest.objects.filter(
            target_product__created_by=self.request.user
        ).select_related(
            'applicant', 'target_product',
            'target_product__host', 'approved_by',
        )

    def get_queryset(self):
        return self.get_provider_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'account_opening'
        context['page_title'] = '开户申请'
        return context


class AccountOpeningRequestListView(ProviderRequestMixin, ListView):
    """
    开户申请列表视图

    - 分页展示
    - 状态筛选
    - 搜索
    - 批量操作（批准 / 驳回）
    """

    model = AccountOpeningRequest
    template_name = 'admin_base/operations/request_list.html'
    context_object_name = 'requests'
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()

        # 状态筛选
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(
                    username__icontains=search[:50],
                    user_fullname__icontains=search[:50],
                    contact_email__icontains=search[:50],
                    applicant__username__icontains=search[:50],
                )
            )

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = (
            AccountOpeningRequest._meta.get_field(
                'status'
            ).choices
        )
        context['current_status'] = (
            self.request.GET.get('status', '')
        )
        context['current_search'] = (
            self.request.GET.get('search', '')
        )
        base_qs = self.get_provider_queryset()
        counts = {
            'pending': base_qs.filter(
                status='pending'
            ).count(),
            'approved': base_qs.filter(
                status='approved'
            ).count(),
            'rejected': base_qs.filter(
                status='rejected'
            ).count(),
            'processing': base_qs.filter(
                status='processing'
            ).count(),
            'completed': base_qs.filter(
                status='completed'
            ).count(),
            'failed': base_qs.filter(
                status='failed'
            ).count(),
        }
        context['status_choices_with_counts'] = [
            (v, l, counts.get(v, 0))
            for v, l in context['status_choices']
        ]
        context['total_count'] = base_qs.count()
        return context


class AccountOpeningRequestDetailView(ProviderRequestMixin, DetailView):
    """
    开户申请详情视图

    展示申请完整信息、状态时间线，以及批准/驳回/执行开户按钮。
    """

    model = AccountOpeningRequest
    template_name = 'admin_base/operations/request_detail.html'
    context_object_name = 'request_obj'

    def get_queryset(self):
        return self.get_provider_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj = self.object
        # 构建状态时间线
        timeline = []
        timeline.append({
            'label': '提交申请',
            'time': obj.created_at,
            'done': True,
        })
        if obj.status in (
            'approved', 'rejected', 'processing',
            'completed', 'failed',
        ):
            timeline.append({
                'label': '审核完成',
                'time': obj.approval_date,
                'done': (
                    obj.status != 'failed'
                    or obj.approval_date is not None
                ),
                'detail': (
                    '批准'
                    if obj.status != 'rejected'
                    else '驳回'
                ),
            })
        if obj.status in ('processing', 'completed', 'failed'):
            timeline.append({
                'label': '执行开户',
                'time': (
                    obj.updated_at
                    if obj.status == 'completed'
                    else None
                ),
                'done': obj.status in ('completed',),
                'detail': (
                    obj.result_message
                    if obj.result_message
                    else None
                ),
            })
        context['timeline'] = timeline
        context['reject_form'] = (
            AccountOpeningRequestRejectForm()
        )
        return context


class AccountOpeningRequestApproveView(ProviderRequestMixin, View):
    """批准单条开户申请 (POST)"""

    def post(self, request, pk):
        obj = get_object_or_404(
            self.get_provider_queryset(), pk=pk
        )
        if obj.status != 'pending':
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，无法批准。',
            )
            return redirect(
                'provider_operations:request_detail',
                pk=obj.pk,
            )

        obj.approve(approver=request.user, notes='')
        messages.success(
            request, f'已批准申请 {obj.username}。',
        )
        return redirect(
            'provider_operations:request_detail',
            pk=obj.pk,
        )


class AccountOpeningRequestRejectView(ProviderRequestMixin, View):
    """
    驳回单条开户申请

    GET: 展示驳回表单
    POST: 提交驳回（含驳回原因）
    """

    def get(self, request, pk):
        obj = get_object_or_404(
            self.get_provider_queryset(), pk=pk
        )
        if obj.status != 'pending':
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，无法驳回。',
            )
            return redirect(
                'provider_operations:request_detail',
                pk=obj.pk,
            )
        form = AccountOpeningRequestRejectForm()
        return render(
            request,
            'admin_base/operations/request_reject.html',
            {
                'request_obj': obj,
                'form': form,
                'active_nav': 'account_opening',
                'page_title': '驳回申请',
            },
        )

    def post(self, request, pk):
        obj = get_object_or_404(
            self.get_provider_queryset(), pk=pk
        )
        if obj.status != 'pending':
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，无法驳回。',
            )
            return redirect(
                'provider_operations:request_detail',
                pk=obj.pk,
            )

        form = AccountOpeningRequestRejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['rejection_reason']
            obj.reject(approver=request.user, notes=reason)
            messages.success(
                request, f'已驳回申请 {obj.username}。',
            )
            return redirect(
                'provider_operations:request_detail',
                pk=obj.pk,
            )

        return render(
            request,
            'admin_base/operations/request_reject.html',
            {
                'request_obj': obj,
                'form': form,
                'active_nav': 'account_opening',
                'page_title': '驳回申请',
            },
        )


class AccountOpeningRequestExecuteView(ProviderRequestMixin, View):
    """
    执行开户操作 (POST)

    对已批准的申请执行实际的用户创建操作。
    """

    def post(self, request, pk):
        obj = get_object_or_404(
            self.get_provider_queryset(), pk=pk
        )
        if obj.status not in ('approved', 'pending'):
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，'
                f'无法执行开户操作。',
            )
            return redirect(
                'provider_operations:request_detail',
                pk=obj.pk,
            )

        try:
            from . import services
            services.execute_account_opening(obj)
            messages.success(
                request,
                f'申请 {obj.username} 开户操作已执行。',
            )
        except Exception as e:
            logger.error(
                f'执行开户失败: {obj.username}, '
                f'错误: {str(e)}',
                exc_info=True,
            )
            messages.error(
                request,
                f'执行开户操作失败: {str(e)}',
            )

        return redirect(
            'provider_operations:request_detail',
            pk=obj.pk,
        )


class AccountOpeningRequestBatchApproveView(ProviderRequestMixin, View):
    """
    批量批准开户申请 (POST)

    请求体需包含 selected_ids。
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何申请。')
            return redirect('provider_operations:request_list')

        qs = self.get_provider_queryset().filter(
            pk__in=selected_ids, status='pending',
        )
        updated_count = 0
        for obj in qs:
            obj.approve(approver=request.user, notes='')
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功批准了 {updated_count} 个开户申请。',
            )
        else:
            messages.warning(
                request,
                '没有符合条件的待审核申请需要批准。',
            )

        return redirect('provider_operations:request_list')


class AccountOpeningRequestBatchRejectView(ProviderRequestMixin, View):
    """
    批量驳回开户申请 (POST)

    请求体需包含 selected_ids 和可选的 rejection_reason。
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何申请。')
            return redirect('provider_operations:request_list')

        rejection_reason = request.POST.get(
            'rejection_reason', '批量驳回',
        )

        qs = self.get_provider_queryset().filter(
            pk__in=selected_ids, status='pending',
        )
        updated_count = 0
        for obj in qs:
            obj.reject(
                approver=request.user, notes=rejection_reason,
            )
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功驳回了 {updated_count} 个开户申请。',
            )
        else:
            messages.warning(
                request,
                '没有符合条件的待审核申请需要驳回。',
            )

        return redirect('provider_operations:request_list')


# ===========================================================================
# 邀请令牌管理
# ===========================================================================


class ProductInvitationTokenListView(ProviderRequestMixin, ListView):
    """
    产品邀请令牌列表视图

    - 提供商数据隔离：只看到自己创建的令牌
    - 支持批量启用/禁用
    - 显示邀请链接和复制按钮
    """

    model = ProductInvitationToken
    template_name = 'admin_base/operations/token_list.html'
    context_object_name = 'tokens'
    paginate_by = 20

    def get_queryset(self):
        return ProductInvitationToken.objects.filter(
            created_by=self.request.user
        ).select_related(
            'product', 'product_group',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'invitation_tokens'
        context['page_title'] = '邀请令牌'
        context['is_provider'] = True

        # 生成邀请链接
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', '')
        for token in context['tokens']:
            token.invite_link = (
                f'{site_url}/operations/invite/{token.token}/'
            )
        return context


class ProductInvitationTokenDetailView(ProviderRequestMixin, DetailView):
    """
    产品邀请令牌详情视图

    - 查看令牌基本信息
    - 查看所有使用该令牌的用户列表（ProductAccessGrant）
    - 提供商数据隔离：只能查看自己创建的令牌
    """

    model = ProductInvitationToken
    template_name = 'admin_base/operations/token_detail.html'
    context_object_name = 'token_obj'

    def get_queryset(self):
        return ProductInvitationToken.objects.filter(
            created_by=self.request.user,
        ).select_related(
            'product', 'product_group', 'created_by',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token_obj = context['token_obj']
        context['active_nav'] = 'invitation_tokens'
        context['page_title'] = '邀请令牌详情'
        context['is_provider'] = True

        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', '')
        token_obj.invite_link = (
            f'{site_url}/operations/invite/{token_obj.token}/'
        )

        grants = ProductAccessGrant.objects.filter(
            granted_by_token=token_obj,
        ).select_related(
            'user', 'product', 'product_group',
        ).order_by('-granted_at')

        from django.core.paginator import Paginator
        paginator = Paginator(grants, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        context['grants'] = page_obj
        context['grant_count'] = grants.count()
        from django.utils import timezone
        context['effective_grant_count'] = grants.filter(
            is_revoked=False,
        ).exclude(
            expires_at__lt=timezone.now(),
        ).count() if grants.exists() else 0
        return context


class ProductInvitationTokenCreateView(ProviderRequestMixin, View):
    """
    创建邀请令牌视图

    GET: 展示创建表单
    POST: 提交创建
    """

    def get(self, request):
        from .forms_provider import ProductInvitationTokenForm
        form = ProductInvitationTokenForm(provider_user=request.user)
        return render(request, 'admin_base/operations/token_create.html', {
            'form': form,
            'active_nav': 'invitation_tokens',
            'page_title': '创建邀请令牌',
        })

    def post(self, request):
        from .forms_provider import ProductInvitationTokenForm
        form = ProductInvitationTokenForm(
            request.POST, provider_user=request.user,
        )
        if form.is_valid():
            token_obj = form.save(commit=False)
            token_obj.created_by = request.user
            token_obj.save()
            messages.success(
                request,
                f'邀请令牌创建成功：{token_obj.token[:8]}...',
            )
            return redirect('provider_operations:token_list')

        return render(request, 'admin_base/operations/token_create.html', {
            'form': form,
            'active_nav': 'invitation_tokens',
            'page_title': '创建邀请令牌',
        })


class ProductInvitationTokenBatchEnableView(ProviderRequestMixin, View):
    """
    批量启用邀请令牌 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何令牌。')
            return redirect('provider_operations:token_list')

        updated_count = ProductInvitationToken.objects.filter(
            pk__in=selected_ids,
            created_by=request.user,
            is_active=False,
        ).update(is_active=True)

        if updated_count > 0:
            messages.success(
                request,
                f'成功启用了 {updated_count} 个邀请令牌。',
            )
        else:
            messages.warning(
                request,
                '没有需要启用的邀请令牌。',
            )

        return redirect('provider_operations:token_list')


class ProductInvitationTokenBatchDisableView(ProviderRequestMixin, View):
    """
    批量禁用邀请令牌 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何令牌。')
            return redirect('provider_operations:token_list')

        updated_count = ProductInvitationToken.objects.filter(
            pk__in=selected_ids,
            created_by=request.user,
            is_active=True,
        ).update(is_active=False)

        if updated_count > 0:
            messages.success(
                request,
                f'成功禁用了 {updated_count} 个邀请令牌。',
            )
        else:
            messages.warning(
                request,
                '没有需要禁用的邀请令牌。',
            )

        return redirect('provider_operations:token_list')


# ===========================================================================
# 访问授权管理
# ===========================================================================


class ProductAccessGrantListView(ProviderRequestMixin, ListView):
    """
    产品访问授权列表视图

    - 提供商数据隔离：只看到自己产品/产品组相关的授权
    - 支持批量撤销
    """

    model = ProductAccessGrant
    template_name = 'admin_base/operations/grant_list.html'
    context_object_name = 'grants'
    paginate_by = 20

    def get_queryset(self):
        return ProductAccessGrant.objects.filter(
            Q(product__created_by=self.request.user)
            | Q(product_group__created_by=self.request.user)
        ).select_related(
            'user', 'product', 'product_group',
            'granted_by_token',
        ).order_by('-granted_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'access_grants'
        context['page_title'] = '访问授权'
        context['is_provider'] = True
        return context


class ProductAccessGrantBatchRevokeView(ProviderRequestMixin, View):
    """
    批量撤销访问授权 (POST)
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何授权记录。')
            return redirect('provider_operations:grant_list')

        from django.utils import timezone
        qs = ProductAccessGrant.objects.filter(
            pk__in=selected_ids,
            is_revoked=False,
        ).filter(
            Q(product__created_by=request.user)
            | Q(product_group__created_by=request.user),
        )

        updated_count = 0
        for grant in qs:
            grant.is_revoked = True
            grant.revoked_at = timezone.now()
            grant.revoked_by = request.user
            grant.save(
                update_fields=['is_revoked', 'revoked_at', 'revoked_by'],
            )
            updated_count += 1

        if updated_count > 0:
            messages.success(
                request,
                f'成功撤销了 {updated_count} 个授权。',
            )
        else:
            messages.warning(
                request,
                '没有需要撤销的授权。',
            )

        return redirect('provider_operations:grant_list')


# ===========================================================================
# RDP 域名路由管理
# ===========================================================================


class RdpDomainRouteListView(ProviderRequestMixin, ListView):
    """
    RDP域名路由列表视图

    - 新增提供商数据隔离：通过 product__created_by 过滤
    - 只读视图，提供商无法修改路由
    """

    model = RdpDomainRoute
    template_name = 'admin_base/operations/route_list.html'
    context_object_name = 'routes'
    paginate_by = 20

    def get_queryset(self):
        return RdpDomainRoute.objects.filter(
            product__created_by=self.request.user
        ).select_related(
            'product', 'assigned_to',
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'domain_routes'
        context['page_title'] = '域名路由'
        return context


# ===========================================================================
# 系统任务（只读参考）
# ===========================================================================


class SystemTaskListView(ProviderRequestMixin, ListView):
    """
    系统任务列表视图

    - 只读参考视图，无独立管理页面
    - 提供商数据隔离：只看到自己创建的任务
    """

    model = SystemTask
    template_name = 'admin_base/operations/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        return SystemTask.objects.filter(
            created_by=self.request.user
        ).order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'activity_log'
        context['page_title'] = '系统任务'
        return context


# ===========================================================================
# 产品管理
# ===========================================================================


class ProviderProductMixin(ProviderContextMixin):
    """
    提供商产品数据隔离 Mixin

    - dispatch: 验证提供商身份
    - get_queryset: 限制为当前提供商创建的产品
    """

    provider_url_namespace = 'provider:provider_operations'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_provider(request.user):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden(
                '您没有提供商权限，无法访问此页面。'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_provider_product_queryset(self):
        """获取当前提供商可见的产品查询集"""
        return Product.objects.filter(
            created_by=self.request.user
        ).select_related(
            'host', 'product_group', 'created_by',
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'products'
        context['page_title'] = '产品管理'
        return context


class ProductListView(ProviderProductMixin, TemplateView):
    """
    产品列表视图

    支持搜索、筛选、分页
    """

    template_name = 'admin_base/operations/product_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        queryset = self.get_provider_product_queryset()

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search)
                | Q(host__name__icontains=search)
            )

        # 可用状态筛选
        available_filter = self.request.GET.get('is_available', '').strip()
        if available_filter:
            queryset = queryset.filter(is_available=available_filter == 'true')

        # 可见性筛选
        visibility_filter = self.request.GET.get('visibility', '').strip()
        if visibility_filter:
            queryset = queryset.filter(visibility=visibility_filter)

        # 排序
        queryset = queryset.order_by('-created_at')

        # 分页
        paginator = Paginator(queryset, 15)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'products': page_obj,
            'search': search,
            'available_filter': available_filter,
            'visibility_filter': visibility_filter,
            'visibility_choices': Product._meta.get_field('visibility').choices,
            'page_title': '产品管理',
            'active_nav': 'products',
        })
        return context


class ProductDetailView(ProviderProductMixin, DetailView):
    """
    产品详情视图

    显示产品信息、磁盘配额配置、关联用户数等
    """

    template_name = 'admin_base/operations/product_detail.html'
    context_object_name = 'product'
    pk_url_kwarg = 'pk'

    def get_queryset(self):
        return self.get_provider_product_queryset()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.object

        # 获取关联用户数
        user_count = CloudComputerUser.objects.filter(
            product=product
        ).count()

        # 磁盘配额信息
        disk_quota_json = '{}'
        if product.default_disk_quota:
            disk_quota_json = json.dumps(
                product.default_disk_quota,
                ensure_ascii=False,
                indent=2,
            )

        extra_disks_json = '[]'
        if product.allow_extra_quota_disks:
            extra_disks_json = json.dumps(
                product.allow_extra_quota_disks,
                ensure_ascii=False,
            )

        context.update({
            'user_count': user_count,
            'disk_quota_json': disk_quota_json,
            'extra_disks_json': extra_disks_json,
            'page_title': f'产品 - {product.display_name}',
            'active_nav': 'products',
        })
        return context


class ProductCreateView(ProviderProductMixin, TemplateView):
    """
    产品创建视图

    处理 GET 和 POST 请求，创建新产品。
    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/operations/product_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get(
                'form',
                ProductForm(provider_user=self.request.user),
            ),
            'page_title': '创建产品',
            'active_nav': 'products',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = ProductForm(
            request.POST,
            provider_user=request.user,
        )
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()

            messages.success(
                request,
                f'产品 {product.display_name} 创建成功',
            )
            return redirect(
                'provider_operations:product_detail',
                pk=product.pk,
            )

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class ProductUpdateView(ProviderProductMixin, TemplateView):
    """
    产品编辑视图

    处理 GET 和 POST 请求，编辑产品信息。
    """

    template_name = 'admin_base/operations/product_form.html'

    def get_product(self):
        """获取当前编辑的产品，确保数据隔离"""
        return get_object_or_404(
            self.get_provider_product_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_product()
        form = kwargs.get(
            'form',
            ProductForm(
                instance=product,
                provider_user=self.request.user,
            ),
        )
        context.update({
            'form': form,
            'product': product,
            'page_title': f'编辑产品 - {product.display_name}',
            'active_nav': 'products',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        product = self.get_product()
        form = ProductForm(
            request.POST,
            instance=product,
            provider_user=request.user,
        )
        if form.is_valid():
            product = form.save()
            messages.success(
                request,
                f'产品 {product.display_name} 更新成功',
            )
            return redirect(
                'provider_operations:product_detail',
                pk=product.pk,
            )

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class ProductDeleteView(ProviderProductMixin, TemplateView):
    """
    产品删除视图

    显示确认页面，处理删除请求。
    """

    template_name = 'admin_base/operations/product_confirm_delete.html'

    def get_product(self):
        return get_object_or_404(
            self.get_provider_product_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_product()

        # 获取关联用户数
        user_count = CloudComputerUser.objects.filter(
            product=product
        ).count()

        context.update({
            'product': product,
            'user_count': user_count,
            'page_title': f'删除产品 - {product.display_name}',
            'active_nav': 'products',
        })
        return context

    def post(self, request, *args, **kwargs):
        product = self.get_product()
        product_name = product.display_name
        product.delete()

        messages.success(
            request,
            f'产品 {product_name} 已删除',
        )
        return redirect('provider_operations:product_list')


# ===========================================================================
# 产品组管理
# ===========================================================================


class ProviderProductGroupMixin(ProviderContextMixin):
    """
    提供商产品组数据隔离 Mixin

    - dispatch: 验证提供商身份
    - get_queryset: 限制为当前提供商创建的产品组
    """

    provider_url_namespace = 'provider:provider_operations'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not is_provider(request.user):
            from django.http import HttpResponseForbidden
            return HttpResponseForbidden(
                '您没有提供商权限，无法访问此页面。'
            )
        return super().dispatch(request, *args, **kwargs)

    def get_provider_productgroup_queryset(self):
        """获取当前提供商可见的产品组查询集"""
        return ProductGroup.objects.filter(
            created_by=self.request.user
        ).order_by('display_order', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'product_groups'
        context['page_title'] = '产品组管理'
        return context


class ProductGroupListView(ProviderProductGroupMixin, TemplateView):
    """
    产品组列表视图

    支持搜索、分页
    """

    template_name = 'admin_base/operations/productgroup_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        queryset = self.get_provider_productgroup_queryset()

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        # 分页
        paginator = Paginator(queryset, 15)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'productgroups': page_obj,
            'search': search,
            'page_title': '产品组管理',
            'active_nav': 'product_groups',
        })
        return context


class ProductGroupCreateView(ProviderProductGroupMixin, TemplateView):
    """
    产品组创建视图

    处理 GET 和 POST 请求，创建新产品组。
    自动设置 created_by 为当前用户。
    """

    template_name = 'admin_base/operations/productgroup_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get(
                'form',
                ProductGroupForm(),
            ),
            'page_title': '创建产品组',
            'active_nav': 'product_groups',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = ProductGroupForm(request.POST)
        if form.is_valid():
            productgroup = form.save(commit=False)
            productgroup.created_by = request.user
            productgroup.save()

            messages.success(
                request,
                f'产品组 {productgroup.name} 创建成功',
            )
            return redirect('provider_operations:productgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class ProductGroupUpdateView(ProviderProductGroupMixin, TemplateView):
    """
    产品组编辑视图

    处理 GET 和 POST 请求，编辑产品组信息。
    """

    template_name = 'admin_base/operations/productgroup_form.html'

    def get_productgroup(self):
        """获取当前编辑的产品组，确保数据隔离"""
        return get_object_or_404(
            self.get_provider_productgroup_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        productgroup = self.get_productgroup()
        form = kwargs.get(
            'form',
            ProductGroupForm(instance=productgroup),
        )
        context.update({
            'form': form,
            'productgroup': productgroup,
            'page_title': f'编辑产品组 - {productgroup.name}',
            'active_nav': 'product_groups',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        productgroup = self.get_productgroup()
        form = ProductGroupForm(request.POST, instance=productgroup)
        if form.is_valid():
            productgroup = form.save()
            messages.success(
                request,
                f'产品组 {productgroup.name} 更新成功',
            )
            return redirect('provider_operations:productgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


class ProductGroupDeleteView(ProviderProductGroupMixin, TemplateView):
    """
    产品组删除视图

    显示确认页面，处理删除请求。
    """

    template_name = 'admin_base/operations/productgroup_confirm_delete.html'

    def get_productgroup(self):
        return get_object_or_404(
            self.get_provider_productgroup_queryset(),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        productgroup = self.get_productgroup()

        # 获取关联产品数
        product_count = Product.objects.filter(
            product_group=productgroup
        ).count()

        context.update({
            'productgroup': productgroup,
            'product_count': product_count,
            'page_title': f'删除产品组 - {productgroup.name}',
            'active_nav': 'product_groups',
        })
        return context

    def post(self, request, *args, **kwargs):
        productgroup = self.get_productgroup()
        productgroup_name = productgroup.name
        productgroup.delete()

        messages.success(
            request,
            f'产品组 {productgroup_name} 已删除',
        )
        return redirect('provider_operations:productgroup_list')
