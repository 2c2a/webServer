"""
自定义错误处理视图
"""
import re
from urllib.parse import urlparse

from django.shortcuts import render, redirect
from django.views.static import serve
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotFound, Http404, HttpResponseBadRequest
import os

from apps.dashboard.models import SystemConfig


def custom_404(request, exception):
    """
    自定义404错误页面

    Args:
        request: HTTP请求对象
        exception: 异常对象

    Returns:
        HttpResponse: 404错误页面
    """
    return render(request, 'errors/404.html', status=404)


def custom_500(request):
    """
    自定义500错误页面

    Args:
        request: HTTP请求对象

    Returns:
        HttpResponse: 500错误页面
    """
    return render(request, 'errors/500.html', status=500)


def _get_default_favicon_path(filename):
    return os.path.join(
        settings.STATIC_ROOT or settings.STATICFILES_DIRS[0],
        'img', filename
    )


def _serve_hostname_favicon(request, default_filename):
    hostname = request.get_host().split(':')[0]
    site_icon = None

    site_group = getattr(request, 'site_group', None)
    if site_group and site_group.site_icon:
        site_icon = site_group.site_icon
    else:
        try:
            config = SystemConfig.get_config()
            site_icon = config.get_site_icon_for_hostname(hostname)
        except Exception:
            site_icon = '/static/img/favicon.svg'

    if site_icon and site_icon != '/static/img/favicon.svg':
        if site_icon.startswith(settings.MEDIA_URL):
            rel_path = site_icon[len(settings.MEDIA_URL):]
            file_path = os.path.join(settings.MEDIA_ROOT, rel_path)
        elif site_icon.startswith('/'):
            file_path = os.path.join(settings.BASE_DIR, site_icon.lstrip('/'))
        else:
            file_path = site_icon

        if os.path.exists(file_path) and os.path.isfile(file_path):
            content_type = 'image/svg+xml'
            if file_path.endswith('.ico'):
                content_type = 'image/x-icon'
            elif file_path.endswith('.png'):
                content_type = 'image/png'
            with open(file_path, 'rb') as f:
                return HttpResponse(f.read(), content_type=content_type)

    favicon_path = _get_default_favicon_path(default_filename)
    if not os.path.exists(favicon_path):
        favicon_path = os.path.join(
            settings.STATICFILES_DIRS[0], 'img', default_filename
        )
    return serve(
        request, os.path.basename(favicon_path),
        document_root=os.path.dirname(favicon_path)
    )


def favicon_view(request):
    return _serve_hostname_favicon(request, 'favicon.ico')


def favicon_svg_view(request):
    return _serve_hostname_favicon(request, 'favicon.svg')


# Static 文件降级服务域名
STATIC_FALLBACK_HOST = 'https://static.2c2a.cc.cd'


def static_fallback_view(request, path):
    """
    生产环境 static 文件降级视图

    逻辑：
    1. 先尝试从本地 STATIC_ROOT 或 STATICFILES_DIRS 中查找并 serve 文件
    2. 如果本地文件不存在，则 302 重定向到外部 static 服务

    Args:
        request: HTTP请求对象
        path: static 文件路径

    Returns:
        HttpResponse: 本地文件或 302 重定向响应
    """
    document_root = None

    if settings.STATIC_ROOT and os.path.exists(settings.STATIC_ROOT):
        document_root = settings.STATIC_ROOT
    elif settings.STATICFILES_DIRS:
        for static_dir in settings.STATICFILES_DIRS:
            if os.path.exists(static_dir):
                document_root = static_dir
                break

    if document_root:
        real_root = os.path.realpath(document_root)
        file_path = os.path.realpath(os.path.join(document_root, path))
        if not file_path.startswith(real_root + os.sep) and file_path != real_root:
            return HttpResponseBadRequest('Invalid path')
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return serve(request, os.path.relpath(file_path, real_root), document_root=real_root)

    sanitized = path.replace('\\', '/')
    parsed = urlparse(sanitized)
    if parsed.scheme or parsed.netloc:
        return HttpResponseBadRequest('Invalid path')

    redirect_url = f"{STATIC_FALLBACK_HOST}/static/{sanitized}"
    return redirect(redirect_url, permanent=False)


USER_DOCS_FILE = settings.BASE_DIR / 'USER_DOCS.md'


def docs_index(request):
    md_text = ''
    if USER_DOCS_FILE.exists():
        with open(USER_DOCS_FILE, 'r', encoding='utf-8') as f:
            md_text = f.read()
    return render(request, 'docs/index.html', {
        'doc_title': '用户手册',
        'md_text': md_text,
    })