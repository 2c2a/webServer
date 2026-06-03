"""
后台认证装饰器

集中管理后台用户的身份验证逻辑。
供整个项目的视图和中间件使用。

- admin_required: 要求用户为超级管理员或提供商（统一后台入口）
- superadmin_required: 要求用户为超级管理员（仅超管可访问的功能）
- provider_required: 要求用户为提供商（已废弃，保留兼容）
"""

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect
from functools import wraps


PROVIDER_GROUP_NAME = '主机提供商'


def is_provider(user):
    """
    检查用户是否属于提供商组

    条件：
    - 用户已认证
    - 用户属于"提供商"组
    - 用户为 staff 成员

    注意：超级管理员不属于提供商组，即使其权限更高。
    此逻辑与 Admin 后台的数据隔离保持一致。

    Args:
        user: 用户对象

    Returns:
        bool: 如果用户满足提供商条件，返回 True
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return False
    if not user.is_staff:
        return False
    return user.groups.filter(name=PROVIDER_GROUP_NAME).exists()


def provider_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME,
                      login_url=None):
    """
    装饰器：要求当前用户为提供商

    验证逻辑：
    - 未登录用户将被重定向到登录页（带 next 参数）
    - 已登录但非提供商用户将收到 403 Forbidden

    用法：
        @provider_required
        def my_view(request):
            ...

        # 或用于类视图
        @method_decorator(provider_required, name='dispatch')
        class MyView(TemplateView):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                path = request.get_full_path()
                return redirect_to_login(
                    path,
                    login_url=login_url,
                    redirect_field_name=redirect_field_name,
                )
            if not is_provider(request.user):
                return HttpResponseForbidden(
                    '您没有提供商权限，无法访问此页面。'
                )
            return func(request, *args, **kwargs)
        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def superadmin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME,
                        login_url=None):
    """
    装饰器：要求当前用户为超级管理员

    验证逻辑：
    - 未登录用户将被重定向到登录页（带 next 参数）
    - 已登录但非超级管理员将收到 403 Forbidden

    用法：
        @superadmin_required
        def my_view(request):
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                path = request.get_full_path()
                return redirect_to_login(
                    path,
                    login_url=login_url,
                    redirect_field_name=redirect_field_name,
                )
            if not request.user.is_superuser:
                return HttpResponseForbidden(
                    '您没有超级管理员权限，无法访问此页面。'
                )
            return func(request, *args, **kwargs)
        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def is_site_group_admin(user, site_group=None):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if site_group is None:
        return False
    return site_group.admins.filter(pk=user.pk).exists()


def site_group_admin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME,
                               login_url=None):
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                path = request.get_full_path()
                return redirect_to_login(
                    path,
                    login_url=login_url,
                    redirect_field_name=redirect_field_name,
                )
            site_group = getattr(request, 'site_group', None)
            if not (request.user.is_superuser or is_site_group_admin(request.user, site_group)):
                return HttpResponseForbidden(
                    '您没有站点组管理员权限，无法访问此页面。'
                )
            return func(request, *args, **kwargs)
        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator


def admin_required(view_func=None, redirect_field_name=REDIRECT_FIELD_NAME,
                   login_url=None):
    """
    装饰器：要求当前用户为后台用户（超级管理员或提供商）

    统一后台入口装饰器，允许超级管理员和提供商访问 /admin/ 路由。
    视图内部通过 request.user.is_superuser 判断角色做数据隔离。

    验证逻辑：
    - 未登录用户将被重定向到登录页（带 next 参数）
    - 已登录但非后台用户将收到 403 Forbidden

    用法：
        @admin_required
        def my_view(request):
            if request.user.is_superuser:
                qs = Model.objects.all()
            else:
                qs = Model.objects.filter(created_by=request.user)
            ...
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from django.contrib.auth.views import redirect_to_login
                path = request.get_full_path()
                return redirect_to_login(
                    path,
                    login_url=login_url,
                    redirect_field_name=redirect_field_name,
                )
            user = request.user
            site_group = getattr(request, 'site_group', None)
            if not (user.is_staff or is_provider(user) or is_site_group_admin(user, site_group)):
                return HttpResponseForbidden(
                    '您没有后台访问权限。'
                )
            return func(request, *args, **kwargs)
        return wrapper

    if view_func:
        return decorator(view_func)
    return decorator
