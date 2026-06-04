"""
提供商共享工具模块

本模块是提供商数据隔离的 SINGLE SOURCE OF TRUTH。
所有提供商相关的身份验证和数据查询逻辑
应统一使用此模块，替代
apps/hosts/admin.py、apps/operations/admin.py、
apps/tickets/admin.py 中重复的 is_provider 函数。

使用方式:
    from utils.provider import (
        is_provider, get_provider_hosts, get_provider_products,
    )
"""

from django.db import models


PROVIDER_GROUP_NAME = "主机提供商"


def is_provider(user):
    """
    检查用户是否属于提供商组

    超级管理员不属于提供商组，即使其权限更高。
    此逻辑与 Admin 后台的数据隔离保持一致。

    Args:
        user: 用户对象

    Returns:
        bool: 如果用户属于提供商组且不是超级管理员，返回 True
    """
    if user.is_superuser:
        return False
    return user.groups.filter(name=PROVIDER_GROUP_NAME).exists()


def get_provider_hosts(user, site_group=None):
    """
    获取提供商管理的主机

    提供商可以看到:
    - 自己创建的主机 (created_by=user)
    - 分配给自己的主机 (providers=user)

    Args:
        user: 提供商用户对象
        site_group: 站点分组对象，如果提供则进一步过滤该站点分组下的主机

    Returns:
        QuerySet: 该提供商可见的主机查询集
    """
    from apps.hosts.models import Host

    qs = Host.objects.filter(
        models.Q(created_by=user) | models.Q(providers=user)
    ).distinct()
    if site_group is not None:
        qs = qs.filter(site_group=site_group)
    return qs


def get_provider_products(user, site_group=None):
    """
    获取提供商创建的产品

    提供商可以看到自己创建的产品 (created_by=user)

    Args:
        user: 提供商用户对象
        site_group: 站点分组对象，如果提供则进一步过滤该站点分组下的产品

    Returns:
        QuerySet: 该提供商可见的产品查询集
    """
    from apps.operations.models import Product

    qs = Product.objects.filter(created_by=user)
    if site_group is not None:
        qs = qs.filter(site_group=site_group)
    return qs


def get_provider_queryset(
    user, model_class, filter_field="created_by", site_group=None
):
    """
    通用的提供商数据隔离查询

    根据模型和过滤字段，返回该提供商可见的数据查询集。
    对于有 providers ManyToManyField 的模型，也会包含分配给该提供商的数据。

    Args:
        user: 提供商用户对象
        model_class: Django 模型类
        filter_field: 过滤字段名，默认为 'created_by'
        site_group: 站点分组对象，如果提供则进一步过滤该站点分组下的数据

    Returns:
        QuerySet: 该提供商可见的数据查询集

    Examples:
        # 获取提供商创建的主机
        get_provider_queryset(user, Host, 'created_by')

        # 获取提供商创建的产品
        get_provider_queryset(user, Product, 'created_by')

        # 获取提供商创建的开户申请（通过产品关联）
        get_provider_queryset(user, AccountOpeningRequest,
                              'target_product__created_by')
    """
    qs = model_class.objects.filter(**{filter_field: user})

    if hasattr(model_class, "providers"):
        qs = qs | model_class.objects.filter(providers=user)
        qs = qs.distinct()

    if site_group is not None:
        qs = qs.filter(site_group=site_group)

    return qs
