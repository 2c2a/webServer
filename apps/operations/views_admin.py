"""
运营管理 - 超级管理员后台视图

包含产品、产品组、开户申请、云电脑用户、邀请令牌、访问授权、
RDP域名路由、系统任务等视图。
所有视图均受超级管理员身份验证保护。
超管可查看所有数据；提供商仅可查看自己创建的数据。
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
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.provider_decorators import admin_required
from utils.provider import get_provider_products
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

from .forms_admin import (
    AdminProductForm,
    AdminProductGroupForm,
    AdminRequestRejectForm,
)

logger = logging.getLogger(__name__)
User = get_user_model()


# ========== 辅助函数 ==========


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
# 产品管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminProductListView(TemplateView):
    """
    超管产品列表视图

    - 查看所有产品（无数据隔离）
    - 搜索、筛选、分页
    - 显示创建者信息
    """

    template_name = 'admin_base/operations/product_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 数据隔离：超管查看所有产品，提供商仅查看自己创建的
        if self.request.user.is_superuser:
            queryset = Product.objects.select_related(
                'host', 'product_group', 'created_by',
            )
        else:
            queryset = get_provider_products(
                self.request.user
            ).select_related(
                'host', 'product_group', 'created_by',
            )

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(display_name__icontains=search)
                | Q(host__name__icontains=search)
                | Q(created_by__username__icontains=search)
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
        paginator = Paginator(queryset, 20)
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
            'active_nav': 'operations_products',
        })
        return context


@method_decorator(admin_required, name='dispatch')
class AdminProductCreateView(TemplateView):
    """
    超管产品创建视图

    处理 GET 和 POST 请求，创建新产品。
    """

    template_name = 'admin_base/operations/product_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get('form', AdminProductForm()),
            'page_title': '创建产品',
            'active_nav': 'operations_products',
            'is_create': True,
            'existing_disk_quota': kwargs.get(
                'existing_disk_quota', '{}'
            ),
            'existing_extra_disks': kwargs.get(
                'existing_extra_disks', '[]'
            ),
            'initial_host_id': kwargs.get(
                'initial_host_id', '""'
            ),
            'enable_disk_quota_initial': kwargs.get(
                'enable_disk_quota_initial', 'false'
            ),
        })
        return context

    def post(self, request, *args, **kwargs):
        form = AdminProductForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()
            messages.success(
                request,
                f'产品 {product.display_name} 创建成功',
            )
            return redirect('admin:admin_operations:product_list')

        return self.render_to_response(
            self.get_context_data(
                form=form,
                existing_disk_quota=request.POST.get(
                    'default_disk_quota', '{}'
                ),
                existing_extra_disks=request.POST.get(
                    'allow_extra_quota_disks', '[]'
                ),
                initial_host_id=json.dumps(
                    request.POST.get('host', '')
                ),
                enable_disk_quota_initial=json.dumps(
                    'enable_disk_quota' in request.POST
                ),
            )
        )


# ========== 产品创建向导 ==========


@admin_required
def admin_product_wizard(request):
    """
    产品创建向导视图

    引导超管分步创建产品：
    - Step 1: 基本信息 (显示名称、描述、产品组)
    - Step 2: 主机关联与配置 (主机、显示地址、RDP端口、可见性、状态)
    - Step 3: 高级设置 (主机保护、磁盘配额、创建预览)

    使用 Alpine.js 在客户端管理步骤切换，
    最终一次性提交表单创建产品。
    """
    from .forms_wizard import ProductWizardForm

    if request.method == 'POST':
        form = ProductWizardForm(request.POST)
        if form.is_valid():
            product = form.save(commit=False)
            product.created_by = request.user
            product.save()

            messages.success(
                request,
                f'产品 {product.display_name} 创建成功',
            )
            return redirect(
                'admin:admin_operations:product_edit',
                pk=product.pk,
            )
    else:
        form = ProductWizardForm()

    hosts_info = form.get_hosts_info()

    context = {
        'form': form,
        'hosts_info': json.dumps(hosts_info),
        'visibility_choices': Product._meta.get_field(
            'visibility'
        ).choices,
        'page_title': '创建产品',
        'active_nav': 'operations_products',
    }

    return render(
        request,
        'admin_base/operations/product_wizard.html',
        context,
    )


@method_decorator(admin_required, name='dispatch')
class AdminProductUpdateView(TemplateView):
    """
    超管产品编辑视图

    处理 GET 和 POST 请求，编辑产品信息。
    """

    template_name = 'admin_base/operations/product_form.html'

    def get_product(self):
        """获取当前编辑的产品，提供商仅可编辑自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(
                Product.objects.select_related(
                    'host', 'product_group', 'created_by'
                ),
                pk=self.kwargs['pk'],
            )
        return get_object_or_404(
            get_provider_products(self.request.user).select_related(
                'host', 'product_group', 'created_by'
            ),
            pk=self.kwargs['pk'],
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        product = self.get_product()
        form = kwargs.get(
            'form',
            AdminProductForm(instance=product),
        )
        context.update({
            'form': form,
            'product': product,
            'page_title': f'编辑产品 - {product.display_name}',
            'active_nav': 'operations_products',
            'is_create': False,
            'existing_disk_quota': kwargs.get(
                'existing_disk_quota',
                json.dumps(product.default_disk_quota or {}),
            ),
            'existing_extra_disks': kwargs.get(
                'existing_extra_disks',
                json.dumps(product.allow_extra_quota_disks or []),
            ),
            'initial_host_id': kwargs.get(
                'initial_host_id',
                json.dumps(product.host_id),
            ),
            'enable_disk_quota_initial': kwargs.get(
                'enable_disk_quota_initial',
                json.dumps(product.enable_disk_quota),
            ),
        })
        return context

    def post(self, request, *args, **kwargs):
        product = self.get_product()
        form = AdminProductForm(request.POST, instance=product)
        if form.is_valid():
            product = form.save()
            messages.success(
                request,
                f'产品 {product.display_name} 更新成功',
            )
            return redirect('admin:admin_operations:product_list')

        return self.render_to_response(
            self.get_context_data(
                form=form,
                existing_disk_quota=request.POST.get(
                    'default_disk_quota', '{}'
                ),
                existing_extra_disks=request.POST.get(
                    'allow_extra_quota_disks', '[]'
                ),
                initial_host_id=json.dumps(
                    request.POST.get('host', '')
                ),
                enable_disk_quota_initial=json.dumps(
                    'enable_disk_quota' in request.POST
                ),
            )
        )


@method_decorator(admin_required, name='dispatch')
class AdminProductDeleteView(TemplateView):
    """
    超管产品删除视图

    显示确认页面，处理删除请求。
    """

    template_name = 'admin_base/operations/product_confirm_delete.html'

    def get_product(self):
        """获取当前删除的产品，提供商仅可删除自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(Product, pk=self.kwargs['pk'])
        return get_object_or_404(
            get_provider_products(self.request.user),
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
            'active_nav': 'operations_products',
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
        return redirect('admin:admin_operations:product_list')


# ===========================================================================
# 产品组管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminProductGroupListView(TemplateView):
    """
    超管产品组列表视图

    - 查看所有产品组（无数据隔离）
    - 搜索、分页
    """

    template_name = 'admin_base/operations/productgroup_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 数据隔离：超管查看所有产品组，提供商仅查看自己创建的
        if self.request.user.is_superuser:
            queryset = ProductGroup.objects.select_related(
                'created_by',
            )
        else:
            queryset = ProductGroup.objects.filter(
                created_by=self.request.user
            ).select_related('created_by')

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
            )

        # 排序
        queryset = queryset.order_by('display_order', 'name')

        # 分页
        paginator = Paginator(queryset, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        context.update({
            'page_obj': page_obj,
            'productgroups': page_obj,
            'search': search,
            'page_title': '产品组管理',
            'active_nav': 'operations_product_groups',
        })
        return context


@method_decorator(admin_required, name='dispatch')
class AdminProductGroupCreateView(TemplateView):
    """
    超管产品组创建视图

    处理 GET 和 POST 请求，创建新产品组。
    """

    template_name = 'admin_base/operations/productgroup_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'form': kwargs.get('form', AdminProductGroupForm()),
            'page_title': '创建产品组',
            'active_nav': 'operations_product_groups',
            'is_create': True,
        })
        return context

    def post(self, request, *args, **kwargs):
        form = AdminProductGroupForm(request.POST)
        if form.is_valid():
            productgroup = form.save(commit=False)
            productgroup.created_by = request.user
            productgroup.save()
            messages.success(
                request,
                f'产品组 {productgroup.name} 创建成功',
            )
            return redirect('admin:admin_operations:productgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminProductGroupUpdateView(TemplateView):
    """
    超管产品组编辑视图

    处理 GET 和 POST 请求，编辑产品组信息。
    """

    template_name = 'admin_base/operations/productgroup_form.html'

    def get_productgroup(self):
        """获取当前编辑的产品组，提供商仅可编辑自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(ProductGroup, pk=self.kwargs['pk'])
        return get_object_or_404(
            ProductGroup, pk=self.kwargs['pk'],
            created_by=self.request.user,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        productgroup = self.get_productgroup()
        form = kwargs.get(
            'form',
            AdminProductGroupForm(instance=productgroup),
        )
        context.update({
            'form': form,
            'productgroup': productgroup,
            'page_title': f'编辑产品组 - {productgroup.name}',
            'active_nav': 'operations_product_groups',
            'is_create': False,
        })
        return context

    def post(self, request, *args, **kwargs):
        productgroup = self.get_productgroup()
        form = AdminProductGroupForm(request.POST, instance=productgroup)
        if form.is_valid():
            productgroup = form.save()
            messages.success(
                request,
                f'产品组 {productgroup.name} 更新成功',
            )
            return redirect('admin:admin_operations:productgroup_list')

        return self.render_to_response(
            self.get_context_data(form=form)
        )


@method_decorator(admin_required, name='dispatch')
class AdminProductGroupDeleteView(TemplateView):
    """
    超管产品组删除视图

    显示确认页面，处理删除请求。
    """

    template_name = 'admin_base/operations/productgroup_confirm_delete.html'

    def get_productgroup(self):
        """获取当前删除的产品组，提供商仅可删除自己创建的"""
        if self.request.user.is_superuser:
            return get_object_or_404(ProductGroup, pk=self.kwargs['pk'])
        return get_object_or_404(
            ProductGroup, pk=self.kwargs['pk'],
            created_by=self.request.user,
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
            'active_nav': 'operations_product_groups',
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
        return redirect('admin:admin_operations:productgroup_list')


# ===========================================================================
# 开户申请管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminRequestListView(ListView):
    """
    超管开户申请列表视图

    - 查看所有开户申请（无数据隔离）
    - 状态筛选、搜索、批量操作
    """

    model = AccountOpeningRequest
    template_name = 'admin_base/operations/request_list.html'
    context_object_name = 'requests'
    paginate_by = 20

    def get_queryset(self):
        qs = AccountOpeningRequest.objects.select_related(
            'applicant', 'target_product',
            'target_product__host', 'approved_by',
        )

        # 数据隔离：提供商仅查看自己产品的开户申请
        if not self.request.user.is_superuser:
            provider_products = get_provider_products(
                self.request.user
            )
            qs = qs.filter(target_product__in=provider_products)

        # 状态筛选
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(username__icontains=search[:50])
                | Q(user_fullname__icontains=search[:50])
                | Q(contact_email__icontains=search[:50])
                | Q(applicant__username__icontains=search[:50])
            )

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['status_choices'] = (
            AccountOpeningRequest._meta.get_field('status').choices
        )
        context['current_status'] = self.request.GET.get('status', '')
        context['current_search'] = self.request.GET.get('search', '')

        # 数据隔离：提供商仅统计自己产品的申请
        if self.request.user.is_superuser:
            base_qs = AccountOpeningRequest.objects.all()
        else:
            provider_products = get_provider_products(
                self.request.user
            )
            base_qs = AccountOpeningRequest.objects.filter(
                target_product__in=provider_products
            )
        counts = {
            'pending': base_qs.filter(status='pending').count(),
            'approved': base_qs.filter(status='approved').count(),
            'rejected': base_qs.filter(status='rejected').count(),
            'processing': base_qs.filter(status='processing').count(),
            'completed': base_qs.filter(status='completed').count(),
            'failed': base_qs.filter(status='failed').count(),
        }
        context['status_choices_with_counts'] = [
            (v, l, counts.get(v, 0))
            for v, l in context['status_choices']
        ]
        context['total_count'] = base_qs.count()
        context['page_title'] = '开户申请'
        context['active_nav'] = 'operations_requests'
        return context


@method_decorator(admin_required, name='dispatch')
class AdminRequestDetailView(DetailView):
    """
    超管开户申请详情视图

    展示申请完整信息、状态时间线，以及批准/驳回按钮。
    """

    model = AccountOpeningRequest
    template_name = 'admin_base/operations/request_detail.html'
    context_object_name = 'request_obj'

    def get_queryset(self):
        """数据隔离：提供商仅可查看自己产品的申请"""
        qs = AccountOpeningRequest.objects.select_related(
            'applicant', 'target_product',
            'target_product__host', 'approved_by',
        )
        if not self.request.user.is_superuser:
            provider_products = get_provider_products(
                self.request.user
            )
            qs = qs.filter(target_product__in=provider_products)
        return qs

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
        context['reject_form'] = AdminRequestRejectForm()
        context['page_title'] = '申请详情'
        context['active_nav'] = 'operations_requests'
        return context


@method_decorator(admin_required, name='dispatch')
class AdminRequestApproveView(View):
    """超管批准单条开户申请 (POST)"""

    def post(self, request, pk):
        # 数据隔离：提供商仅可批准自己产品的申请
        if request.user.is_superuser:
            obj = get_object_or_404(AccountOpeningRequest, pk=pk)
        else:
            provider_products = get_provider_products(request.user)
            obj = get_object_or_404(
                AccountOpeningRequest, pk=pk,
                target_product__in=provider_products,
            )
        if obj.status != 'pending':
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，无法批准。',
            )
            return redirect('admin:admin_operations:request_detail', pk=obj.pk)

        obj.approve(approver=request.user, notes='')
        messages.success(request, f'已批准申请 {obj.username}。')
        return redirect('admin:admin_operations:request_detail', pk=obj.pk)


@method_decorator(admin_required, name='dispatch')
class AdminRequestRejectView(View):
    """
    超管驳回单条开户申请

    POST: 提交驳回（含驳回原因）
    """

    def post(self, request, pk):
        # 数据隔离：提供商仅可驳回自己产品的申请
        if request.user.is_superuser:
            obj = get_object_or_404(AccountOpeningRequest, pk=pk)
        else:
            provider_products = get_provider_products(request.user)
            obj = get_object_or_404(
                AccountOpeningRequest, pk=pk,
                target_product__in=provider_products,
            )
        if obj.status != 'pending':
            messages.warning(
                request,
                f'申请 {obj.username} 当前状态为'
                f' {obj.get_status_display()}，无法驳回。',
            )
            return redirect('admin:admin_operations:request_detail', pk=obj.pk)

        form = AdminRequestRejectForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data['rejection_reason']
            obj.reject(approver=request.user, notes=reason)
            messages.success(request, f'已驳回申请 {obj.username}。')
            return redirect('admin:admin_operations:request_detail', pk=obj.pk)

        messages.error(request, '请输入驳回原因。')
        return redirect('admin:admin_operations:request_detail', pk=obj.pk)


@method_decorator(admin_required, name='dispatch')
class AdminRequestBatchApproveView(View):
    """
    超管批量批准开户申请 (POST)

    请求体需包含 selected_ids。
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何申请。')
            return redirect('admin:admin_operations:request_list')

        qs = AccountOpeningRequest.objects.filter(
            pk__in=selected_ids, status='pending',
        )
        # 数据隔离：提供商仅可批准自己产品的申请
        if not request.user.is_superuser:
            provider_products = get_provider_products(request.user)
            qs = qs.filter(target_product__in=provider_products)
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

        return redirect('admin:admin_operations:request_list')


@method_decorator(admin_required, name='dispatch')
class AdminRequestBatchRejectView(View):
    """
    超管批量驳回开户申请 (POST)

    请求体需包含 selected_ids 和可选的 rejection_reason。
    """

    def post(self, request):
        selected_ids = _get_selected_ids(request)
        if not selected_ids:
            messages.warning(request, '未选择任何申请。')
            return redirect('admin:admin_operations:request_list')

        rejection_reason = request.POST.get(
            'rejection_reason', '批量驳回',
        )

        qs = AccountOpeningRequest.objects.filter(
            pk__in=selected_ids, status='pending',
        )
        # 数据隔离：提供商仅可驳回自己产品的申请
        if not request.user.is_superuser:
            provider_products = get_provider_products(request.user)
            qs = qs.filter(target_product__in=provider_products)
        updated_count = 0
        for obj in qs:
            obj.reject(approver=request.user, notes=rejection_reason)
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

        return redirect('admin:admin_operations:request_list')


# ===========================================================================
# 云电脑用户管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminCloudUserListView(TemplateView):
    """
    超管云电脑用户列表视图

    - 查看所有云电脑用户（无数据隔离）
    - 搜索、状态筛选、产品筛选
    """

    template_name = 'admin_base/operations/user_list.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 数据隔离：超管查看所有用户，提供商仅查看自己产品的用户
        if self.request.user.is_superuser:
            queryset = CloudComputerUser.objects.select_related(
                'product',
                'product__host',
                'created_from_request',
                'created_from_request__applicant',
                'owner',
            )
        else:
            provider_products = get_provider_products(
                self.request.user
            )
            queryset = CloudComputerUser.objects.filter(
                product__in=provider_products
            ).select_related(
                'product',
                'product__host',
                'created_from_request',
                'created_from_request__applicant',
                'owner',
            )

        # 搜索
        search = self.request.GET.get('search', '').strip()
        if search:
            q_filter = (
                Q(username__icontains=search)
                | Q(fullname__icontains=search)
                | Q(email__icontains=search)
                | Q(product__display_name__icontains=search)
            )
            queryset = queryset.filter(q_filter).distinct()

        # 状态筛选
        status_filter = self.request.GET.get('status', '').strip()
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # 产品筛选
        product_filter = self.request.GET.get('product', '').strip()
        if product_filter:
            queryset = queryset.filter(product_id=product_filter)

        # 排序
        queryset = queryset.order_by('-created_at')

        # 分页
        paginator = Paginator(queryset, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)

        # 状态选项
        status_choices = CloudComputerUser._meta.get_field('status').choices

        # 数据隔离：产品下拉列表
        if self.request.user.is_superuser:
            products_for_filter = Product.objects.all().order_by(
                'display_name'
            )
        else:
            products_for_filter = get_provider_products(
                self.request.user
            ).order_by('display_name')

        context.update({
            'page_obj': page_obj,
            'users': page_obj,
            'search': search,
            'status_filter': status_filter,
            'product_filter': product_filter,
            'status_choices': status_choices,
            'products': products_for_filter,
            'page_title': '云电脑用户',
            'active_nav': 'operations_users',
        })

        return context


@method_decorator(admin_required, name='dispatch')
class AdminCloudUserDetailView(DetailView):
    """
    超管云电脑用户详情视图

    显示用户信息、管理员状态、磁盘配额等
    """

    model = CloudComputerUser
    template_name = 'admin_base/operations/user_detail.html'
    context_object_name = 'cloud_user'

    def get_queryset(self):
        qs = CloudComputerUser.objects.select_related(
            'product',
            'product__host',
            'created_from_request',
            'created_from_request__applicant',
            'owner',
        )
        # 数据隔离：提供商仅可查看自己产品的用户
        if not self.request.user.is_superuser:
            provider_products = get_provider_products(
                self.request.user
            )
            qs = qs.filter(product__in=provider_products)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cloud_user = self.object

        context.update({
            'page_title': f'用户详情 - {cloud_user.username}',
            'active_nav': 'operations_users',
            'disk_quota_json': json.dumps(
                cloud_user.disk_quota, ensure_ascii=False
            ) if cloud_user.disk_quota else '{}',
        })

        return context


@admin_required
def admin_cloud_user_action(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    qs = CloudComputerUser.objects.select_related('product', 'product__host')
    if not request.user.is_superuser:
        provider_products = get_provider_products(request.user)
        qs = qs.filter(product__in=provider_products)

    cloud_user = get_object_or_404(qs, pk=pk)

    if cloud_user.status == 'deleted':
        return JsonResponse({'success': False, 'message': '已删除的用户无法执行操作'})

    action = request.POST.get('action', '')

    if action == 'disable':
        cloud_user.disable()
        cloud_user.refresh_from_db()
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 已封禁',
            'status': cloud_user.status,
        })

    elif action == 'enable':
        if cloud_user.status != 'disabled':
            return JsonResponse({'success': False, 'message': '仅已封禁的用户可以解封'})
        cloud_user.activate()
        cloud_user.refresh_from_db()
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 已解封',
            'status': cloud_user.status,
        })

    elif action == 'delete':
        cloud_user.delete_user()
        cloud_user.refresh_from_db()
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 已删除',
            'status': cloud_user.status,
        })

    elif action == 'set_admin':
        if cloud_user.is_admin:
            return JsonResponse({'success': False, 'message': '该用户已是管理员'})
        cloud_user.is_admin = True
        cloud_user.save(update_fields=['is_admin', 'updated_at'])
        try:
            host = cloud_user.product.host
            client = host.get_connection_client()
            client.op_user(cloud_user.username)
        except Exception as e:
            logger.error(f'远程设置管理员失败: {e}')
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 已设为管理员',
            'is_admin': True,
        })

    elif action == 'remove_admin':
        if not cloud_user.is_admin:
            return JsonResponse({'success': False, 'message': '该用户不是管理员'})
        cloud_user.is_admin = False
        cloud_user.save(update_fields=['is_admin', 'updated_at'])
        try:
            host = cloud_user.product.host
            client = host.get_connection_client()
            client.deop_user(cloud_user.username)
        except Exception as e:
            logger.error(f'远程取消管理员失败: {e}')
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 已取消管理员',
            'is_admin': False,
        })

    elif action == 'reset_password':
        new_password = CloudComputerUser.generate_complex_password()
        cloud_user.initial_password = new_password
        cloud_user.password_viewed = False
        cloud_user.password_viewed_at = None
        cloud_user.save(update_fields=['initial_password', 'password_viewed', 'password_viewed_at', 'updated_at'])
        try:
            cloud_user.reset_windows_password(new_password)
        except Exception as e:
            logger.error(f'远程重置密码失败: {e}')
        return JsonResponse({
            'success': True,
            'message': f'用户 {cloud_user.username} 密码已重置',
            'new_password': new_password,
        })

    else:
        return JsonResponse({'success': False, 'message': '无效的操作类型'}, status=400)


@admin_required
def admin_cloud_user_set_quota(request, pk):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': '仅支持 POST 请求'}, status=405)

    qs = CloudComputerUser.objects.select_related('product', 'product__host')
    if not request.user.is_superuser:
        provider_products = get_provider_products(request.user)
        qs = qs.filter(product__in=provider_products)

    cloud_user = get_object_or_404(qs, pk=pk)

    if not cloud_user.product.enable_disk_quota:
        return JsonResponse({'success': False, 'message': '该产品未启用磁盘配额管理'})

    disk = request.POST.get('disk', '').strip().upper()
    quota_str = request.POST.get('quota', '').strip()

    if not disk or not quota_str:
        return JsonResponse({'success': False, 'message': '磁盘盘符和配额值不能为空'})

    try:
        quota_mb = int(quota_str)
        if quota_mb < 0:
            return JsonResponse({'success': False, 'message': '配额值不能为负数'})
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'message': '配额值必须为数字'})

    import re
    if not re.match(r'^[A-Za-z]:\\?$', disk):
        return JsonResponse({'success': False, 'message': f'无效的磁盘盘符: {disk}'})
    disk = disk.rstrip('\\')

    new_quota = dict(cloud_user.disk_quota) if cloud_user.disk_quota else {}
    new_quota[disk] = quota_mb
    cloud_user.disk_quota = new_quota
    cloud_user.save(update_fields=['disk_quota', 'updated_at'])

    try:
        from utils.disk_quota import set_disk_quota_via_client
        host = cloud_user.product.host
        client = host.get_connection_client()
        result = set_disk_quota_via_client(client, cloud_user.username, disk, quota_mb)
        if not result['success']:
            return JsonResponse({'success': False, 'message': f'远程设置配额失败: {result["message"]}'})
    except Exception as e:
        logger.error(f'远程设置磁盘配额失败: {e}', exc_info=True)
        return JsonResponse({'success': False, 'message': '远程设置配额失败'})

    return JsonResponse({
        'success': True,
        'message': f'磁盘 {disk} 配额已设置为 {quota_mb} MB',
        'disk': disk,
        'quota': quota_mb,
    })


# ===========================================================================
# 邀请令牌管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminTokenListView(ListView):
    """
    超管邀请令牌列表视图

    - 查看所有邀请令牌（无数据隔离）
    - 显示邀请链接
    """

    model = ProductInvitationToken
    template_name = 'admin_base/operations/token_list.html'
    context_object_name = 'tokens'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductInvitationToken.objects.select_related(
            'product', 'product_group', 'created_by',
        )
        # 数据隔离：提供商仅可查看自己创建的令牌
        if not self.request.user.is_superuser:
            qs = qs.filter(created_by=self.request.user)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'operations_tokens'
        context['page_title'] = '邀请令牌'

        # 生成邀请链接
        from django.conf import settings
        site_url = getattr(settings, 'SITE_URL', '')
        for token in context['tokens']:
            token.invite_link = (
                f'{site_url}/operations/invite/{token.token}/'
            )
        return context


@method_decorator(admin_required, name='dispatch')
class AdminTokenDetailView(DetailView):
    """
    超管邀请令牌详情视图

    - 查看令牌基本信息
    - 查看所有使用该令牌的用户列表（ProductAccessGrant）
    """

    model = ProductInvitationToken
    template_name = 'admin_base/operations/token_detail.html'
    context_object_name = 'token_obj'

    def get_queryset(self):
        qs = ProductInvitationToken.objects.select_related(
            'product', 'product_group', 'created_by',
        )
        # 数据隔离：提供商仅可查看自己创建的令牌
        if not self.request.user.is_superuser:
            qs = qs.filter(created_by=self.request.user)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        token_obj = context['token_obj']
        context['active_nav'] = 'operations_tokens'
        context['page_title'] = '邀请令牌详情'

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

        paginator = Paginator(grants, 20)
        page_number = self.request.GET.get('page', 1)
        page_obj = paginator.get_page(page_number)
        context['grants'] = page_obj
        context['grant_count'] = grants.count()
        context['effective_grant_count'] = grants.filter(
            is_revoked=False,
        ).exclude(
            expires_at__lt=timezone.now(),
        ).count() if grants.exists() else 0
        return context


# ===========================================================================
# 访问授权管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminGrantListView(ListView):
    """
    超管访问授权列表视图

    - 查看所有访问授权（无数据隔离）
    """

    model = ProductAccessGrant
    template_name = 'admin_base/operations/grant_list.html'
    context_object_name = 'grants'
    paginate_by = 20

    def get_queryset(self):
        qs = ProductAccessGrant.objects.select_related(
            'user', 'product', 'product_group',
            'granted_by_token',
        )
        # 数据隔离：提供商仅可查看自己产品的授权
        if not self.request.user.is_superuser:
            provider_products = get_provider_products(
                self.request.user
            )
            qs = qs.filter(product__in=provider_products)
        return qs.order_by('-granted_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'operations_grants'
        context['page_title'] = '访问授权'
        return context


# ===========================================================================
# RDP 域名路由管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminRouteListView(ListView):
    """
    超管RDP域名路由列表视图

    - 查看所有域名路由（无数据隔离）
    - 只读视图
    """

    model = RdpDomainRoute
    template_name = 'admin_base/operations/route_list.html'
    context_object_name = 'routes'
    paginate_by = 20

    def get_queryset(self):
        qs = RdpDomainRoute.objects.select_related(
            'product', 'assigned_to',
        )
        # 数据隔离：提供商仅可查看自己产品的路由
        if not self.request.user.is_superuser:
            provider_products = get_provider_products(
                self.request.user
            )
            qs = qs.filter(product__in=provider_products)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'operations_routes'
        context['page_title'] = '域名路由'
        return context


# ===========================================================================
# 系统任务管理
# ===========================================================================


@method_decorator(admin_required, name='dispatch')
class AdminTaskListView(ListView):
    """
    超管系统任务列表视图

    - 查看所有系统任务（无数据隔离）
    - 只读参考视图
    """

    model = SystemTask
    template_name = 'admin_base/operations/task_list.html'
    context_object_name = 'tasks'
    paginate_by = 20

    def get_queryset(self):
        qs = SystemTask.objects.select_related(
            'created_by',
        )
        # 数据隔离：提供商仅可查看自己创建的任务
        if not self.request.user.is_superuser:
            qs = qs.filter(created_by=self.request.user)
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['active_nav'] = 'operations_tasks'
        context['page_title'] = '系统任务'
        return context
