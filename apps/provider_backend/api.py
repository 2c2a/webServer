from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator

from .decorators import provider_required, is_provider


@method_decorator(provider_required, name='dispatch')
class HostDeployAPI(APIView):
    """
    主机部署 API

    POST /api/hosts/<pk>/deploy/
    生成部署命令
    """

    def post(self, request, pk):
        from apps.hosts.models import Host
        site_group = getattr(request, 'site_group', None)
        host_qs = Host.objects.filter(pk=pk, providers=request.user)
        if site_group:
            host_qs = host_qs.filter(site_group=site_group)
        else:
            host_qs = host_qs.filter(site_group__isnull=True)
        try:
            host = host_qs.get()
        except Host.DoesNotExist:
            return Response(
                {'error': '主机不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        # TODO: 实现部署命令生成逻辑
        return Response({
            'status': 'success',
            'message': f'主机 {host.name} 部署命令生成功能即将上线',
            'host_id': host.pk,
            'host_name': host.name,
        })


@method_decorator(provider_required, name='dispatch')
class AccountRequestActionAPI(APIView):
    """
    开户申请操作 API

    POST /api/account-requests/<pk>/action/
    操作类型: approve / reject / process
    """

    def post(self, request, pk):
        from apps.operations.models import AccountOpeningRequest
        try:
            account_request = AccountOpeningRequest.objects.get(
                pk=pk,
                target_product__created_by=request.user
            )
        except AccountOpeningRequest.DoesNotExist:
            return Response(
                {'error': '开户申请不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        if action not in ('approve', 'reject', 'process'):
            return Response(
                {'error': '无效的操作类型，支持: approve, reject, process'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: 实现开户申请操作逻辑
        return Response({
            'status': 'success',
            'message': f'开户申请 {account_request.pk} 的 {action} 操作即将上线',
            'request_id': account_request.pk,
            'action': action,
        })


@method_decorator(provider_required, name='dispatch')
class CloudUserActionAPI(APIView):
    """
    云电脑用户操作 API

    POST /api/cloud-users/<pk>/action/
    操作类型: activate / deactivate / disable / reset-password
    """

    def post(self, request, pk):
        from apps.operations.models import CloudComputerUser
        site_group = getattr(request, 'site_group', None)
        qs = CloudComputerUser.objects.filter(
            pk=pk,
            product__created_by=request.user
        )
        if site_group:
            qs = qs.filter(product__site_group=site_group)
        else:
            qs = qs.filter(product__site_group__isnull=True)
        try:
            cloud_user = qs.get()
        except CloudComputerUser.DoesNotExist:
            return Response(
                {'error': '云电脑用户不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        valid_actions = ('activate', 'deactivate', 'disable', 'reset-password')
        if action not in valid_actions:
            return Response(
                {'error': f'无效的操作类型，支持: {", ".join(valid_actions)}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: 实现云电脑用户操作逻辑
        return Response({
            'status': 'success',
            'message': f'云电脑用户 {cloud_user.username} 的 {action} 操作即将上线',
            'user_id': cloud_user.pk,
            'username': cloud_user.username,
            'action': action,
        })


@method_decorator(provider_required, name='dispatch')
class InvitationTokenActionAPI(APIView):
    """
    邀请令牌操作 API

    POST /api/invitation-tokens/<pk>/action/
    操作类型: activate / deactivate
    """

    def post(self, request, pk):
        from apps.operations.models import ProductInvitationToken
        try:
            token = ProductInvitationToken.objects.get(
                pk=pk,
                created_by=request.user
            )
        except ProductInvitationToken.DoesNotExist:
            return Response(
                {'error': '邀请令牌不存在'},
                status=status.HTTP_404_NOT_FOUND
            )

        action = request.data.get('action')
        if action not in ('activate', 'deactivate'):
            return Response(
                {'error': '无效的操作类型，支持: activate, deactivate'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # TODO: 实现邀请令牌操作逻辑
        return Response({
            'status': 'success',
            'message': f'邀请令牌 {token.token[:8]}... 的 {action} 操作即将上线',
            'token_id': token.pk,
            'action': action,
        })


class ProductShareLinkAPI(APIView):
    """
    产品分享链接 API

    GET /api/products/<pk>/share-link/
    获取产品的邀请令牌信息（检查是否已有活跃令牌）

    POST /api/products/<pk>/share-link/
    为产品创建新的邀请令牌并返回分享链接
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not (request.user.is_superuser or is_provider(request.user)):
            return Response(
                {'error': '权限不足'},
                status=status.HTTP_403_FORBIDDEN,
            )
        from apps.operations.models import Product, ProductInvitationToken
        site_group = getattr(request, 'site_group', None)
        product_qs = Product.objects.filter(
            pk=pk,
            created_by=request.user,
            visibility='invite_only',
        )
        if site_group:
            product_qs = product_qs.filter(site_group=site_group)
        else:
            product_qs = product_qs.filter(site_group__isnull=True)
        try:
            product = product_qs.get()
        except Product.DoesNotExist:
            return Response(
                {'error': '产品不存在或非邀请访问产品'},
                status=status.HTTP_404_NOT_FOUND,
            )

        active_token = ProductInvitationToken.objects.filter(
            product=product,
            created_by=request.user,
            is_active=True,
        ).order_by('-created_at').first()

        if active_token:
            invite_link = request.build_absolute_uri(
                f'/operations/invite/{active_token.token}/'
            )
            return Response({
                'has_existing': True,
                'invite_link': invite_link,
                'token': active_token.token[:8] + '...',
                'used_count': active_token.used_count,
                'max_uses': active_token.max_uses,
                'created_at': active_token.created_at.isoformat(),
                'expires_at': (
                    active_token.expires_at.isoformat()
                    if active_token.expires_at else None
                ),
            })

        return Response({'has_existing': False})

    def post(self, request, pk):
        if not (request.user.is_superuser or is_provider(request.user)):
            return Response(
                {'error': '权限不足'},
                status=status.HTTP_403_FORBIDDEN,
            )
        from apps.operations.models import Product, ProductInvitationToken
        site_group = getattr(request, 'site_group', None)
        product_qs = Product.objects.filter(
            pk=pk,
            created_by=request.user,
            visibility='invite_only',
        )
        if site_group:
            product_qs = product_qs.filter(site_group=site_group)
        else:
            product_qs = product_qs.filter(site_group__isnull=True)
        try:
            product = product_qs.get()
        except Product.DoesNotExist:
            return Response(
                {'error': '产品不存在或非邀请访问产品'},
                status=status.HTTP_404_NOT_FOUND,
            )

        token_obj = ProductInvitationToken.objects.create(
            product=product,
            created_by=request.user,
            is_active=True,
        )

        invite_link = request.build_absolute_uri(
            f'/operations/invite/{token_obj.token}/'
        )

        return Response({
            'has_existing': False,
            'invite_link': invite_link,
            'token': token_obj.token[:8] + '...',
            'used_count': 0,
            'max_uses': 0,
            'created_at': token_obj.created_at.isoformat(),
            'expires_at': None,
        })
