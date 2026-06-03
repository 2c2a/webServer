from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DetailView, FormView
from django.utils.decorators import method_decorator
from django.shortcuts import redirect

from .decorators import provider_required


@method_decorator(provider_required, name='dispatch')
class ProviderBaseView:
    """提供商后台基础视图混入类，自动应用 provider_required 装饰器"""
    pass


# ========== 仪表盘 ==========

class DashboardView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '仪表盘'
        return context


# ========== 主机管理 ==========

from apps.hosts.models import Host, HostGroup


class HostListView(ProviderBaseView, ListView):
    model = Host
    template_name = 'admin_base/provider/host_list.html'
    context_object_name = 'hosts'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Host.objects.filter(
            providers=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '主机管理'
        return context


class HostCreateWizard(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/host_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建主机'
        return context


class HostDetailView(ProviderBaseView, DetailView):
    model = Host
    template_name = 'admin_base/provider/host_detail.html'
    context_object_name = 'host'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Host.objects.filter(providers=self.request.user)
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '主机详情'
        return context


class HostUpdateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/host_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑主机'
        site_group = getattr(self.request, 'site_group', None)
        qs = Host.objects.filter(
            pk=kwargs['pk'], providers=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        context['host'] = qs.first()
        return context


class HostDeployView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/host_deploy.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '部署主机'
        site_group = getattr(self.request, 'site_group', None)
        qs = Host.objects.filter(
            pk=kwargs['pk'], providers=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        context['host'] = qs.first()
        return context


# ========== 主机组管理 ==========

class HostGroupListView(ProviderBaseView, ListView):
    model = HostGroup
    template_name = 'admin_base/provider/hostgroup_list.html'
    context_object_name = 'hostgroups'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = HostGroup.objects.filter(
            providers=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '主机组管理'
        return context


class HostGroupCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/hostgroup_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建主机组'
        return context


class HostGroupUpdateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/hostgroup_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑主机组'
        site_group = getattr(self.request, 'site_group', None)
        qs = HostGroup.objects.filter(
            pk=kwargs['pk'], providers=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        context['hostgroup'] = qs.first()
        return context


# ========== 产品管理 ==========

from apps.operations.models import (
    Product, ProductGroup, AccountOpeningRequest,
    CloudComputerUser, ProductInvitationToken, ProductAccessGrant,
    RdpDomainRoute,
)


class ProductListView(ProviderBaseView, ListView):
    model = Product
    template_name = 'admin_base/provider/product_list.html'
    context_object_name = 'products'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Product.objects.filter(
            created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '产品管理'
        return context


class ProductCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/product_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建产品'
        return context


class ProductDetailView(ProviderBaseView, DetailView):
    model = Product
    template_name = 'admin_base/provider/product_detail.html'
    context_object_name = 'product'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Product.objects.filter(created_by=self.request.user)
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '产品详情'
        return context


class ProductUpdateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/product_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑产品'
        site_group = getattr(self.request, 'site_group', None)
        qs = Product.objects.filter(
            pk=kwargs['pk'], created_by=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        context['product'] = qs.first()
        return context


# ========== 产品组管理 ==========

class ProductGroupListView(ProviderBaseView, ListView):
    model = ProductGroup
    template_name = 'admin_base/provider/productgroup_list.html'
    context_object_name = 'productgroups'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = ProductGroup.objects.filter(
            created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '产品组管理'
        return context


class ProductGroupCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/productgroup_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建产品组'
        return context


class ProductGroupUpdateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/productgroup_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑产品组'
        site_group = getattr(self.request, 'site_group', None)
        qs = ProductGroup.objects.filter(
            pk=kwargs['pk'], created_by=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        context['productgroup'] = qs.first()
        return context


# ========== 开户申请管理 ==========

class AccountRequestListView(ProviderBaseView, ListView):
    model = AccountOpeningRequest
    template_name = 'admin_base/provider/accountrequest_list.html'
    context_object_name = 'account_requests'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = AccountOpeningRequest.objects.filter(
            target_product__created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(target_product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '开户申请'
        return context


class AccountRequestDetailView(ProviderBaseView, DetailView):
    model = AccountOpeningRequest
    template_name = 'admin_base/provider/accountrequest_detail.html'
    context_object_name = 'account_request'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = AccountOpeningRequest.objects.filter(
            target_product__created_by=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(target_product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '开户申请详情'
        return context


# ========== 云电脑用户管理 ==========

class CloudUserListView(ProviderBaseView, ListView):
    model = CloudComputerUser
    template_name = 'admin_base/provider/clouduser_list.html'
    context_object_name = 'cloud_users'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = CloudComputerUser.objects.filter(
            product__created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '云电脑用户'
        return context


class CloudUserDetailView(ProviderBaseView, DetailView):
    model = CloudComputerUser
    template_name = 'admin_base/provider/clouduser_detail.html'
    context_object_name = 'cloud_user'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = CloudComputerUser.objects.filter(
            product__created_by=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '云电脑用户详情'
        return context


# ========== 邀请令牌管理 ==========

class InvitationTokenListView(ProviderBaseView, ListView):
    model = ProductInvitationToken
    template_name = 'admin_base/provider/invitationtoken_list.html'
    context_object_name = 'invitation_tokens'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = ProductInvitationToken.objects.filter(
            created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '邀请令牌'
        return context


class InvitationTokenCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/invitationtoken_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建邀请令牌'
        return context


# ========== 访问授权管理 ==========

class AccessGrantListView(ProviderBaseView, ListView):
    model = ProductAccessGrant
    template_name = 'admin_base/provider/accessgrant_list.html'
    context_object_name = 'access_grants'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = ProductAccessGrant.objects.filter(
            product__created_by=self.request.user
        ).order_by('-granted_at')
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '访问授权'
        return context


# ========== 工单管理 ==========

from apps.tickets.models import Ticket, TicketCategory, TicketActivity


class TicketListView(ProviderBaseView, ListView):
    model = Ticket
    template_name = 'admin_base/provider/ticket_list.html'
    context_object_name = 'tickets'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Ticket.objects.filter(
            assignee=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '工单管理'
        return context


class TicketCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/ticket_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建工单'
        return context


class TicketDetailView(ProviderBaseView, DetailView):
    model = Ticket
    template_name = 'admin_base/provider/ticket_detail.html'
    context_object_name = 'ticket'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = Ticket.objects.filter(
            assignee=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '工单详情'
        return context


# ========== 工单分类 ==========

class TicketCategoryListView(ProviderBaseView, ListView):
    model = TicketCategory
    template_name = 'admin_base/provider/ticketcategory_list.html'
    context_object_name = 'ticket_categories'

    def get_queryset(self):
        return TicketCategory.objects.filter(
            is_active=True
        ).order_by('display_order', 'name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '工单分类'
        return context


# ========== 工单活动 ==========

class TicketActivityListView(ProviderBaseView, ListView):
    model = TicketActivity
    template_name = 'admin_base/provider/ticketactivity_list.html'
    context_object_name = 'ticket_activities'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = TicketActivity.objects.filter(
            ticket__assignee=self.request.user
        ).order_by('-created_at')[:50]
        if site_group is not None:
            qs = qs.filter(ticket__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '工单活动'
        return context


# ========== RDP路由 ==========

class RdpRouteListView(ProviderBaseView, ListView):
    model = RdpDomainRoute
    template_name = 'admin_base/provider/rdproute_list.html'
    context_object_name = 'rdp_routes'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = RdpDomainRoute.objects.filter(
            product__created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'RDP路由'
        return context


# ========== QQ验证配置 ==========

from plugins.models import QQVerificationConfig


class QQConfigListView(ProviderBaseView, ListView):
    model = QQVerificationConfig
    template_name = 'admin_base/provider/qqconfig_list.html'
    context_object_name = 'qq_configs'

    def get_queryset(self):
        site_group = getattr(self.request, 'site_group', None)
        qs = QQVerificationConfig.objects.filter(
            product__created_by=self.request.user
        ).order_by('-created_at')
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'QQ验证配置'
        return context


class QQConfigCreateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/qqconfig_create.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '创建QQ验证配置'
        return context


class QQConfigUpdateView(ProviderBaseView, TemplateView):
    template_name = 'admin_base/provider/qqconfig_update.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = '编辑QQ验证配置'
        site_group = getattr(self.request, 'site_group', None)
        qs = QQVerificationConfig.objects.filter(
            pk=kwargs['pk'], product__created_by=self.request.user
        )
        if site_group is not None:
            qs = qs.filter(product__site_group=site_group)
        context['qq_config'] = qs.first()
        return context
