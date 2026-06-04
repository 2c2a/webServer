"""
操作记录视图
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, DetailView
from django.utils.decorators import method_decorator
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse, HttpResponseForbidden
import logging

logger = logging.getLogger(__name__)
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from datetime import timedelta
from .models import AccountOpeningRequest, SystemTask, CloudComputerUser, Product
from .forms import (
    AccountOpeningRequestForm,
    AccountOpeningRequestFilterForm,
    CloudComputerUserFilterForm,
)
from apps.hosts.models import Host


@method_decorator(login_required, name="dispatch")
class SystemTaskListView(ListView):
    """系统任务列表视图"""

    model = SystemTask
    template_name = "operations/systemtask_list.html"
    context_object_name = "tasks"
    paginate_by = 20

    def get_queryset(self):
        """获取查询集"""
        queryset = SystemTask.objects.all()

        # 应用过滤条件
        form = SystemTaskFilterForm(self.request.GET)
        if form.is_valid():
            task_type = form.cleaned_data.get("task_type")
            status = form.cleaned_data.get("status")
            start_date = form.cleaned_data.get("start_date")
            end_date = form.cleaned_data.get("end_date")

            if task_type:
                queryset = queryset.filter(task_type__icontains=task_type[:50])
            if status:
                queryset = queryset.filter(status=status)
            if start_date:
                queryset = queryset.filter(created_at__gte=start_date)
            if end_date:
                # 包含结束日期的整天
                end_date = end_date + timedelta(days=1)
                queryset = queryset.filter(created_at__lt=end_date)

        return queryset.select_related("created_by").order_by("-created_at")

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context["filter_form"] = SystemTaskFilterForm(self.request.GET)
        return context


@method_decorator(login_required, name="dispatch")
class SystemTaskDetailView(DetailView):
    """系统任务详情视图"""

    model = SystemTask
    template_name = "operations/systemtask_detail.html"
    context_object_name = "task"


@login_required
def task_progress(request, task_id):
    """
    获取任务进度

    Args:
        request: HTTP请求对象
        task_id: 任务ID

    Returns:
        JsonResponse: JSON格式的响应
    """
    try:
        task = SystemTask.objects.get(pk=task_id)
        return JsonResponse(
            {
                "success": True,
                "data": {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "progress": task.progress,
                    "result": task.result,
                    "error_message": task.error_message,
                },
            }
        )
    except SystemTask.DoesNotExist:
        return JsonResponse({"success": False, "message": "任务不存在"})


@method_decorator(login_required, name="dispatch")
class AccountOpeningRequestCreateView(CreateView):
    """创建开户申请视图"""

    model = AccountOpeningRequest
    form_class = AccountOpeningRequestForm
    template_name = "operations/account_opening_request_form.html"
    success_url = reverse_lazy("operations:account_opening_confirm")

    def get_form_kwargs(self):
        """获取表单初始化参数"""
        kwargs = super().get_form_kwargs()

        # 获取目标产品ID参数
        target_product_id = self.request.GET.get("target_product")
        target_host_id = self.request.GET.get("target_host")  # 兼容旧参数

        # 获取可用产品查询集
        site_group = getattr(self.request, "site_group", None)
        if site_group:
            products_qs = Product.objects.filter(
                is_available=True, site_group=site_group
            )
        else:
            products_qs = Product.objects.filter(
                is_available=True, site_group__isnull=True
            )

        # 如果指定了特定产品，限制查询集
        if target_product_id:
            try:
                if site_group:
                    target_product = Product.objects.filter(site_group=site_group).get(
                        id=target_product_id, is_available=True
                    )
                else:
                    target_product = Product.objects.get(
                        id=target_product_id, is_available=True, site_group__isnull=True
                    )
                products_qs = Product.objects.filter(id=target_product.id)
            except Product.DoesNotExist:
                pass
        elif target_host_id:
            # 兼容旧参数：如果通过target_host指定，则找出关联的产品
            try:
                from apps.hosts.models import Host

                host = Host.objects.get(id=target_host_id)
                # 获取与该主机关联的所有可用产品
                if site_group:
                    products_qs = Product.objects.filter(
                        host=host, is_available=True, site_group=site_group
                    )
                else:
                    products_qs = Product.objects.filter(
                        host=host, is_available=True, site_group__isnull=True
                    )
            except Host.DoesNotExist:
                pass

        # 将产品查询集传递给表单
        kwargs["products_qs"] = products_qs
        return kwargs

    def form_valid(self, form):
        """表单验证成功后的处理"""
        # 将表单数据存储到session中以供确认页面使用
        confirm_data = {
            "contact_email": self.request.user.email,  # 使用当前用户的邮箱，而不是从表单获取
            "username": form.cleaned_data["username"],
            "user_fullname": form.cleaned_data["user_fullname"],
            "user_description": form.cleaned_data["user_description"],
            "target_product_id": form.cleaned_data["target_product"].id,
            "target_product_name": form.cleaned_data["target_product"].display_name,
            "requested_disk_capacity": form.cleaned_data.get(
                "requested_disk_capacity", {}
            ),
        }
        self.request.session["confirm_data"] = confirm_data

        # 重定向到确认页面，而不是直接保存
        return redirect("operations:account_opening_confirm")

    def form_invalid(self, form):
        """表单验证失败后的处理"""
        messages.error(self.request, "开户申请信息填写有误，请检查输入信息。")
        return super().form_invalid(form)


@login_required
def account_opening_confirm(request):
    """开户申请确认页面"""
    confirm_data = request.session.get("confirm_data")
    if not confirm_data:
        messages.error(request, "未找到待确认的申请信息，请重新填写申请。")
        return redirect("operations:account_opening_create")

    context = {"confirm_data": confirm_data}
    return render(request, "operations/account_opening_confirm.html", context)


@csrf_protect
@require_POST
@login_required
def account_opening_submit(request):
    """提交开户申请"""
    confirm_data = request.session.get("confirm_data")
    if not confirm_data:
        messages.error(request, "未找到待提交的申请信息。")
        logger.warning(
            f"用户 {request.user.username} 尝试提交开户申请，但未找到确认数据"
        )
        return redirect("operations:account_opening_create")

    # 创建开户申请对象
    account_request = AccountOpeningRequest()
    account_request.applicant = request.user
    account_request.contact_email = (
        request.user.email
    )  # 使用当前用户的邮箱，而不是表单中的数据
    account_request.username = confirm_data["username"]
    account_request.user_fullname = confirm_data["user_fullname"]
    account_request.user_email = request.user.email  # 使用当前用户的邮箱
    account_request.user_description = confirm_data["user_description"]
    account_request.requested_disk_capacity = confirm_data.get(
        "requested_disk_capacity", {}
    )
    # 移除了requested_password字段，由系统自动生成

    # 设置目标产品
    try:
        site_group = getattr(request, "site_group", None)
        if site_group:
            target_product = Product.objects.filter(site_group=site_group).get(
                id=confirm_data["target_product_id"]
            )
        else:
            target_product = Product.objects.get(
                id=confirm_data["target_product_id"], site_group__isnull=True
            )
        account_request.target_product = target_product
        logger.info(
            f"用户 {request.user.username} 提交开户申请，目标产品: {target_product.name}, 用户名: {account_request.username}, 联系邮箱: {account_request.contact_email}"
        )
    except Product.DoesNotExist:
        messages.error(request, "指定的目标产品不存在。")
        logger.error(
            f'用户 {request.user.username} 尝试提交申请，但目标产品ID {confirm_data["target_product_id"]} 不存在'
        )
        return redirect("operations:account_opening_create")

    try:
        logger.info(f"准备保存开户申请，当前状态: {account_request.status}")
        account_request.save()
        logger.info(
            f"开户申请已保存，ID: {account_request.id}, 最终状态: {account_request.status}"
        )
        messages.success(request, "开户申请已成功提交，请等待审核。")

        # 清除session中的确认数据
        del request.session["confirm_data"]

        return redirect("operations:account_opening_list")
    except Exception as e:
        logger.error(f"提交申请时发生错误: {str(e)}", exc_info=True)
        messages.error(request, "提交申请时发生错误，请稍后重试")
        return redirect("operations:account_opening_create")


class AccountOpeningRequestListView(ListView):
    """开户申请列表视图"""

    model = AccountOpeningRequest
    template_name = "operations/account_opening_request_list.html"
    context_object_name = "requests"
    paginate_by = 20

    def get_queryset(self):
        """获取查询集"""
        queryset = AccountOpeningRequest.objects.all()

        site_group = getattr(self.request, "site_group", None)
        if site_group:
            queryset = queryset.filter(target_product__site_group=site_group)
        else:
            queryset = queryset.filter(target_product__site_group__isnull=True)

        if self.request.user.is_authenticated:
            if not (self.request.user.is_staff or self.request.user.is_superuser):
                queryset = queryset.filter(applicant=self.request.user)
        else:
            # 未认证用户不显示任何申请
            queryset = queryset.none()

        # 应用过滤条件
        form = AccountOpeningRequestFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        if form.is_valid():
            status = form.cleaned_data.get("status")
            if status:
                queryset = queryset.filter(status=status)

            host = form.cleaned_data.get("host")
            if host:
                # 查询与该主机相关的产品的申请
                queryset = queryset.filter(target_product__host=host)

            search = form.cleaned_data.get("search")
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search[:50])
                    | Q(user_fullname__icontains=search[:50])
                    | Q(contact_email__icontains=search[:50])
                )

        return queryset.select_related(
            "applicant", "target_product", "target_product__host", "approved_by"
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context["filter_form"] = AccountOpeningRequestFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        context["statuses"] = AccountOpeningRequest._meta.get_field("status").choices

        # 如果是管理员，显示所有主机；否则只显示与用户申请相关的产品的主机
        site_group = getattr(self.request, "site_group", None)
        if self.request.user.is_authenticated and (
            self.request.user.is_staff or self.request.user.is_superuser
        ):
            if site_group:
                context["hosts"] = Host.objects.filter(site_group=site_group)
            else:
                context["hosts"] = Host.objects.filter(site_group__isnull=True)
        elif self.request.user.is_authenticated:
            host_qs = Host.objects.filter(
                product__accountopeningrequest__applicant=self.request.user
            ).distinct()
            if site_group:
                host_qs = host_qs.filter(site_group=site_group)
            else:
                host_qs = host_qs.filter(site_group__isnull=True)
            context["hosts"] = host_qs
        else:
            context["hosts"] = Host.objects.none()

        return context


@login_required
def account_opening_detail(request, pk):
    """查看开户申请详情"""
    site_group = getattr(request, "site_group", None)
    if site_group:
        account_request = get_object_or_404(
            AccountOpeningRequest.objects.filter(
                Q(target_product__site_group=site_group)
            ),
            pk=pk,
        )
    else:
        account_request = get_object_or_404(
            AccountOpeningRequest, pk=pk, target_product__site_group__isnull=True
        )

    # 检查权限：用户只能查看自己提交的申请
    if account_request.applicant != request.user and not (
        request.user.is_staff or request.user.is_superuser
    ):
        messages.error(request, "您没有权限查看此申请的详情。")
        return redirect("operations:account_opening_list")

    timeline = []
    timeline.append(
        {
            "label": "提交申请",
            "time": account_request.created_at,
            "done": True,
        }
    )
    if account_request.status in (
        "approved",
        "rejected",
        "processing",
        "completed",
        "failed",
    ):
        timeline.append(
            {
                "label": "审核完成",
                "time": account_request.approval_date,
                "done": (
                    account_request.status != "failed"
                    or account_request.approval_date is not None
                ),
                "detail": ("批准" if account_request.status != "rejected" else "驳回"),
            }
        )
    if account_request.status in ("processing", "completed", "failed"):
        timeline.append(
            {
                "label": "执行开户",
                "time": (
                    account_request.updated_at
                    if account_request.status == "completed"
                    else None
                ),
                "done": account_request.status in ("completed",),
                "detail": (
                    account_request.result_message
                    if account_request.result_message
                    else None
                ),
            }
        )

    context = {
        "request": account_request,
        "timeline": timeline,
    }
    return render(request, "operations/account_opening_request_detail.html", context)


@method_decorator(login_required, name="dispatch")
class CloudComputerUserListView(ListView):
    """云电脑用户列表视图"""

    model = CloudComputerUser
    template_name = "operations/cloud_computer_user_list.html"
    context_object_name = "cloud_users"
    paginate_by = 20

    def get_queryset(self):
        """获取查询集"""
        queryset = CloudComputerUser.objects.all()

        site_group = getattr(self.request, "site_group", None)
        if site_group:
            queryset = queryset.filter(product__site_group=site_group)
        else:
            queryset = queryset.filter(product__site_group__isnull=True)

        form = CloudComputerUserFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        if form.is_valid():
            status = form.cleaned_data.get("status")
            if status:
                queryset = queryset.filter(status=status)

            product = form.cleaned_data.get("product")
            if product:
                queryset = queryset.filter(product=product)

            search = form.cleaned_data.get("search")
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search[:50])
                    | Q(fullname__icontains=search[:50])
                    | Q(email__icontains=search[:50])
                )

        return queryset.select_related(
            "product", "created_from_request__applicant"
        ).order_by("-created_at")

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context["filter_form"] = CloudComputerUserFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        context["statuses"] = CloudComputerUser._meta.get_field("status").choices
        site_group = getattr(self.request, "site_group", None)
        if site_group:
            context["products"] = Product.objects.filter(site_group=site_group)
        else:
            context["products"] = Product.objects.filter(site_group__isnull=True)
        return context


# 已删除：toggle_cloud_user_status
# 用户状态切换功能已迁移至 Django Admin 的 Action 实现


@method_decorator(login_required, name="dispatch")
class MyCloudComputersView(ListView):
    """我的云电脑用户列表视图

    显示当前用户拥有的云电脑用户
    """

    model = CloudComputerUser
    template_name = "operations/my_cloud_computers.html"
    context_object_name = "cloud_users"
    paginate_by = 20

    def get_queryset(self):
        """获取查询集 - 只显示当前用户通过开户申请创建的云电脑用户"""
        queryset = CloudComputerUser.objects.filter(
            created_from_request__applicant=self.request.user
        )

        site_group = getattr(self.request, "site_group", None)
        if site_group:
            queryset = queryset.filter(product__site_group=site_group)
        else:
            queryset = queryset.filter(product__site_group__isnull=True)

        form = CloudComputerUserFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        if form.is_valid():
            status = form.cleaned_data.get("status")
            if status:
                queryset = queryset.filter(status=status)

            search = form.cleaned_data.get("search")
            if search:
                queryset = queryset.filter(
                    Q(username__icontains=search)
                    | Q(fullname__icontains=search)
                    | Q(email__icontains=search)
                    | Q(product__display_name__icontains=search)
                )

        # 按产品筛选
        product_filter = self.request.GET.get("product")
        if product_filter:
            queryset = queryset.filter(product__display_name=product_filter)

        return queryset.select_related("product", "created_from_request").order_by(
            "-created_at"
        )

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context["filter_form"] = CloudComputerUserFilterForm(
            self.request.GET,
            site_group=getattr(self.request, "site_group", None),
        )
        context["statuses"] = CloudComputerUser._meta.get_field("status").choices

        context["current_product"] = self.request.GET.get("product", "")
        context["current_search"] = self.request.GET.get("search", "")
        context["current_status"] = self.request.GET.get("status", "")

        from collections import defaultdict

        cloud_users_by_product = defaultdict(list)
        for user in context["cloud_users"]:
            cloud_users_by_product[user.product.display_name].append(user)
        context["cloud_users_by_product"] = dict(cloud_users_by_product)

        return context


@login_required
def my_cloud_computer_detail(request, pk):
    """我的云电脑用户详情页面"""
    cloud_user = get_object_or_404(CloudComputerUser, pk=pk)

    # 权限检查：owner优先，兼容旧数据用created_from_request
    if cloud_user.owner:
        if cloud_user.owner != request.user:
            return HttpResponseForbidden("无权访问")
    elif cloud_user.created_from_request:
        if cloud_user.created_from_request.applicant != request.user:
            return HttpResponseForbidden("无权访问")
    else:
        return HttpResponseForbidden("无权访问")

    context = {"cloud_user": cloud_user}
    return render(request, "operations/my_cloud_computer_detail.html", context)


@login_required
@require_POST
def get_password_and_burn(request, pk):
    """获取密码并销毁 - 阅后即焚"""
    cloud_user = get_object_or_404(CloudComputerUser, pk=pk)

    # 权限检查
    has_access = False
    if cloud_user.owner and cloud_user.owner == request.user:
        has_access = True
    elif (
        cloud_user.created_from_request
        and cloud_user.created_from_request.applicant == request.user
    ):
        has_access = True

    if not has_access:
        return JsonResponse({"success": False, "error": "无权访问"}, status=403)

    try:
        password = cloud_user.get_and_burn_password()
        return JsonResponse({"success": True, "password": password})
    except Exception as e:
        logger.error(f"获取密码失败: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "error": "Failed to retrieve password"})


@login_required
def get_product_disk_config(request, product_id):
    """获取产品的磁盘配额配置"""
    try:
        site_group = getattr(request, "site_group", None)
        if site_group:
            product = Product.objects.filter(site_group=site_group).get(
                pk=product_id, is_available=True
            )
        else:
            product = Product.objects.get(
                pk=product_id, is_available=True, site_group__isnull=True
            )
    except Product.DoesNotExist:
        return JsonResponse({"success": False, "error": "产品不存在"}, status=404)

    return JsonResponse(
        {
            "success": True,
            "data": {
                "enable_disk_quota": product.enable_disk_quota,
                "default_disk_quota": product.default_disk_quota,
                "allow_extra_quota_disks": product.allow_extra_quota_disks,
            },
        }
    )


@login_required
def get_host_disk_info(request, host_id):
    """获取主机的磁盘信息"""

    site_group = getattr(request, "site_group", None)
    host_qs = Host.objects.filter(pk=host_id)
    if site_group:
        host_qs = host_qs.filter(site_group=site_group)
    else:
        host_qs = host_qs.filter(site_group__isnull=True)
    try:
        host = host_qs.get()
    except Host.DoesNotExist:
        return JsonResponse({"success": False, "error": "主机不存在"}, status=404)

    if not request.user.is_superuser and not request.user.is_staff:
        if (
            not host.administrators.filter(pk=request.user.pk).exists()
            and not host.providers.filter(pk=request.user.pk).exists()
        ):
            return JsonResponse({"success": False, "error": "无权访问"}, status=403)

    try:
        from apps.operations.tasks import remote_get_disk_info

        result = remote_get_disk_info.delay(host_id, operator_id=request.user.pk)
        return JsonResponse(
            {
                "success": True,
                "task_id": result.id,
                "message": "磁盘信息获取已提交，正在后台执行",
            }
        )
    except Exception as e:
        logger.error(f"Error dispatching disk info task: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "error": "Failed to get disk info"})


def product_invite_view(request, token):
    """
    产品邀请链接视图

    用户访问邀请链接后，解锁对应产品或产品组的访问权限
    GET: 显示邀请信息和确认页面
    POST: 确认接受邀请，执行授权操作
    """
    from django.shortcuts import render, redirect
    from django.contrib import messages
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    from django.db.models import Q
    from .models import ProductInvitationToken, ProductAccessGrant

    User = get_user_model()

    site_group = getattr(request, "site_group", None)
    if site_group:
        invite_token = (
            ProductInvitationToken.objects.filter(token=token)
            .filter(
                Q(product__site_group=site_group)
                | Q(product_group__site_group=site_group)
            )
            .first()
        )
    else:
        invite_token = (
            ProductInvitationToken.objects.filter(token=token)
            .filter(
                Q(product__site_group__isnull=True)
                | Q(product_group__site_group__isnull=True)
            )
            .first()
        )

    if not invite_token:
        return render(
            request,
            "operations/invite_result.html",
            {
                "success": False,
                "message": "邀请链接无效或不存在。",
            },
        )

    if not invite_token.is_valid():
        if invite_token.is_expired():
            return render(
                request,
                "operations/invite_result.html",
                {
                    "success": False,
                    "message": "邀请链接已过期。",
                },
            )
        if invite_token.is_exhausted():
            return render(
                request,
                "operations/invite_result.html",
                {
                    "success": False,
                    "message": "邀请链接已达到最大使用次数。",
                },
            )
        return render(
            request,
            "operations/invite_result.html",
            {
                "success": False,
                "message": "邀请链接已被禁用。",
            },
        )

    if not request.user.is_authenticated:
        login_url = reverse("accounts:login") + f"?next={request.path}"
        return redirect(login_url)

    existing_grant = ProductAccessGrant.objects.filter(
        user=request.user,
        product=invite_token.product,
        product_group=invite_token.product_group,
        is_revoked=False,
    ).first()

    if existing_grant and not existing_grant.is_expired():
        return render(
            request,
            "operations/invite_result.html",
            {
                "success": True,
                "message": "您已经拥有该产品的访问权限。",
                "product": invite_token.product,
                "product_group": invite_token.product_group,
            },
        )

    if request.method == "GET":
        target_name = (
            invite_token.product.display_name
            if invite_token.product
            else (
                invite_token.product_group.name
                if invite_token.product_group
                else "未知"
            )
        )
        return render(
            request,
            "operations/invite_result.html",
            {
                "success": None,
                "message": f'您即将解锁 "{target_name}" 的访问权限。',
                "product": invite_token.product,
                "product_group": invite_token.product_group,
                "needs_confirm": True,
                "token": token,
            },
        )

    try:
        grant, created = ProductAccessGrant.objects.get_or_create(
            user=request.user,
            product=invite_token.product,
            product_group=invite_token.product_group,
            defaults={
                "granted_by_token": invite_token,
                "expires_at": invite_token.expires_at,
            },
        )
        if not created:
            if grant.is_revoked or grant.is_expired():
                grant.is_revoked = False
                grant.revoked_at = None
                grant.revoked_by = None
                grant.granted_by_token = invite_token
                grant.expires_at = invite_token.expires_at
                grant.save(
                    update_fields=[
                        "is_revoked",
                        "revoked_at",
                        "revoked_by",
                        "granted_by_token",
                        "expires_at",
                    ]
                )
    except Exception as e:
        logger.error(f"创建授权记录失败: {str(e)}", exc_info=True)
        return render(
            request,
            "operations/invite_result.html",
            {
                "success": False,
                "message": "授权处理失败，请稍后重试。",
            },
        )

    invite_token.increment_usage()

    target_name = (
        invite_token.product.display_name
        if invite_token.product
        else (invite_token.product_group.name if invite_token.product_group else "未知")
    )

    return render(
        request,
        "operations/invite_result.html",
        {
            "success": True,
            "message": f'恭喜！您已成功解锁 "{target_name}" 的访问权限。',
            "product": invite_token.product,
            "product_group": invite_token.product_group,
        },
    )


@login_required
def rdp_connect(request, product_id):
    from django.http import HttpResponse
    from django.conf import settings
    from utils.gateway_client import GatewayClient
    from apps.dashboard.models import SystemConfig

    site_group = getattr(request, "site_group", None)
    if site_group:
        product = get_object_or_404(
            Product.objects.filter(site_group=site_group), pk=product_id
        )
    else:
        product = get_object_or_404(Product, pk=product_id, site_group__isnull=True)

    cloud_user = (
        CloudComputerUser.objects.filter(
            product=product,
            status="active",
        )
        .filter(Q(owner=request.user) | Q(created_from_request__applicant=request.user))
        .first()
    )

    if cloud_user is None:
        messages.error(request, "您没有访问此云电脑的权限。")
        return redirect("operations:my_cloud_computers")

    host = product.host
    if not host or not host.tunnel_token:
        messages.error(request, "该产品关联的主机未配置隧道，无法通过RD Gateway连接。")
        return redirect("operations:my_cloud_computers")

    gateway_address = getattr(settings, "GATEWAY_ADDRESS", "rdp.2c2a.com")
    gateway_port = getattr(settings, "GATEWAY_PORT", 443)
    expires_in = getattr(settings, "GATEWAY_PAA_TOKEN_EXPIRY_SECONDS", 600)

    client_ip = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip()
    if not client_ip:
        client_ip = request.META.get("REMOTE_ADDR")

    client = GatewayClient()
    paa_token = client.issue_paa_token(
        user_email=request.user.email,
        tunnel_token=host.tunnel_token,
        client_ip=client_ip,
        expires_in=expires_in,
    )

    rdp_content = client.generate_rdp_file(
        gateway_address=gateway_address,
        gateway_port=gateway_port,
        user_email=request.user.email,
        paa_token=paa_token,
    )

    filename = f"{product.display_name}.rdp"
    response = HttpResponse(rdp_content, content_type="application/x-rdp")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
