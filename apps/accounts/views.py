"""
用户管理视图
"""
from django.shortcuts import redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.generic import CreateView, UpdateView, TemplateView
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.core.cache import cache
from django.utils.http import url_has_allowed_host_and_scheme
from PIL import Image
import os

from .models import User, RegistrationLink
from .forms import UserRegistrationForm, UserUpdateForm, UserLoginForm
from . import rate_limit
from apps.themes.models import ThemeConfig, PageContent


def get_theme_context():
    """获取主题上下文，避免重复代码"""
    theme_config = ThemeConfig.get_config()
    return {
        'theme_config': theme_config,
        'theme_css_url': f'css/themes/{theme_config.active_theme}.css',
        'custom_css_vars': theme_config.generate_css_variables(),
        'page_contents': PageContent.get_all_enabled(),
    }


def get_captcha_context(scene):
    from apps.dashboard.models import SystemConfig
    sc = SystemConfig.get_config()
    captcha_provider, captcha_type = sc.get_captcha_config(scene=scene)
    ctx = {
        'CAPTCHA_PROVIDER': captcha_provider,
        'CAPTCHA_TYPE': captcha_type,
    }
    if scene in ('register', 'forgot_password'):
        _, email_type = sc.get_captcha_config(scene='email')
        ctx['CAPTCHA_TYPE_EMAIL'] = email_type
    return ctx


@method_decorator(rate_limit.register_rate_limit, name='dispatch')
class RegisterView(CreateView):
    """用户注册视图"""

    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_captcha_context('register'))
        context.update(get_theme_context())
        return context

    def form_valid(self, form):
        """表单验证成功后的处理"""
        # 在保存用户之前，验证邮箱验证码（行为验证码在获取邮箱验证码时已验证）
        request = self.request
        # 从表单中获取email，而不是从POST数据中获取
        email = form.cleaned_data.get('email')
        email_code = request.POST.get('email_code')
        if not (email and email_code):
            form.add_error(None, '邮箱验证码缺失')
            return self.form_invalid(form)

        import hmac
        cache_key = f'register_email_code:{email}'
        expected = cache.get(cache_key)
        if expected is None:
            form.add_error(None, '邮箱验证码已过期或不存在')
            return self.form_invalid(form)
        if not hmac.compare_digest(str(expected), str(email_code)):
            form.add_error(None, '邮箱验证码错误')
            return self.form_invalid(form)

        # Optionally clear the code to prevent reuse
        cache.delete(cache_key)

        response = super().form_valid(form)
        messages.success(
            self.request,
            '注册成功！请登录您的账户。'
        )
        return response

    def form_invalid(self, form):
        """表单验证失败后的处理"""
        messages.error(
            self.request,
            '注册失败，请检查表单中的错误。'
        )
        return super().form_invalid(form)


@method_decorator(rate_limit.login_rate_limit, name='dispatch')
class LoginView(TemplateView):
    """用户登录视图"""

    template_name = 'accounts/login.html'

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context['form'] = UserLoginForm()
        context.update(get_captcha_context('login'))
        context['is_demo_mode'] = getattr(self.request, 'is_demo_mode', False)
        context['next'] = self.request.POST.get('next') or self.request.GET.get('next', '')
        context.update(get_theme_context())
        return context

    def post(self, request, *args, **kwargs):
        """处理POST请求"""
        form = UserLoginForm(request.POST)

        if form.is_valid():
            from .captcha_service import validate_captcha
            is_valid, error_msg = validate_captcha(request, scene='login')

            if not is_valid:
                form.add_error(None, error_msg)
                context = self.get_context_data(**kwargs)
                context['form'] = form
                return self.render_to_response(context)

            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            remember = form.cleaned_data.get('remember', False)

            from django.contrib.auth import authenticate
            user = authenticate(request, username=username, password=password)

            if user is not None:
                # 更新最后登录IP
                from django.utils import timezone
                user.last_login = timezone.now()
                user.last_login_ip = self.get_client_ip(request)
                user.save(update_fields=['last_login', 'last_login_ip'])

                # 登录用户
                login(request, user)

                # 设置会话过期时间
                if not remember:
                    request.session.set_expiry(0)  # 浏览器关闭后过期
                else:
                    request.session.set_expiry(60 * 60 * 24 * 7)  # 7天

                messages.success(request, f'欢迎回来，{user.username}！')
                next_url = request.POST.get('next') or request.GET.get('next')
                if next_url and url_has_allowed_host_and_scheme(
                    next_url,
                    allowed_hosts=request.get_host(),
                ):
                    return redirect(next_url)
                if user.is_staff or user.is_superuser:
                    return redirect('/admin/')
                return redirect('dashboard:index')
            else:
                messages.error(request, '用户名或密码错误')

        context = self.get_context_data(**kwargs)
        context['form'] = form
        return self.render_to_response(context)

    def get_client_ip(self, request):
        from utils.helpers import get_client_ip as _get_client_ip
        return _get_client_ip(request)


@method_decorator(login_required, name='dispatch')
class ProfileView(UpdateView):
    """用户资料视图"""

    model = User
    form_class = UserUpdateForm
    template_name = 'accounts/profile.html'
    success_url = reverse_lazy('accounts:profile')

    def get_object(self, queryset=None):
        """获取当前用户对象"""
        return self.request.user

    def form_valid(self, form):
        """表单验证成功后的处理"""
        messages.success(
            self.request,
            '个人资料更新成功！'
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        """表单验证失败后的处理"""
        messages.error(
            self.request,
            '个人资料更新失败，请检查表单中的错误。'
        )
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_demo_mode'] = getattr(self.request, 'is_demo_mode', False)
        return context

    def post(self, request, *args, **kwargs):
        """处理POST请求，包括资料更新和密码修改"""
        # 检查是否是密码修改请求
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        # 检查是否是密码修改请求
        if current_password or new_password or confirm_password:
            # 检查是否在DEMO模式下
            if hasattr(request, 'is_demo_mode') and request.is_demo_mode:
                from django.contrib import messages
                messages.error(request, 'DEMO模式下不允许修改密码')
                # 返回GET请求以显示表单和错误消息
                return super().get(request, *args, **kwargs)
            
            # 验证密码字段
            if not current_password:
                return JsonResponse({'status': 'error', 'message': '请输入当前密码'})
            if not new_password:
                return JsonResponse({'status': 'error', 'message': '请输入新密码'})
            if new_password != confirm_password:
                return JsonResponse(
                    {'status': 'error', 'message': '两次输入的新密码不一致'}
                )
            
            # 验证当前密码是否正确
            user = request.user
            if not user.check_password(current_password):
                return JsonResponse({'status': 'error', 'message': '当前密码错误'})
            
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError as ValError
            try:
                validate_password(new_password, user=user)
            except ValError as e:
                return JsonResponse(
                    {'status': 'error', 'message': e.messages[0]}
                )

            user.set_password(new_password)
            user.save()
            
            return JsonResponse(
                {'status': 'success', 'message': '密码修改成功，请重新登录'}
            )
        
        # 否则是资料更新请求
        return super().post(request, *args, **kwargs)


@login_required
def logout_view(request):
    """用户登出视图"""
    logout(request)
    messages.success(request, '您已成功登出')
    return redirect('accounts:login')


@login_required
@require_http_methods(["POST"])
@rate_limit.general_api_rate_limit
def password_change_api(request):
    """密码更改API端点"""
    if hasattr(request, 'is_demo_mode') and request.is_demo_mode:
        return JsonResponse({'status': 'error', 'message': 'DEMO模式下不允许修改密码'})
    
    current_password = request.POST.get('current_password')
    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')
    
    # 验证密码字段
    if not current_password:
        return JsonResponse({'status': 'error', 'message': '请输入当前密码'})
    if not new_password:
        return JsonResponse({'status': 'error', 'message': '请输入新密码'})
    if new_password != confirm_password:
        return JsonResponse({'status': 'error', 'message': '两次输入的新密码不一致'})
    
    # 验证当前密码是否正确
    user = request.user
    if not user.check_password(current_password):
        return JsonResponse({'status': 'error', 'message': '当前密码错误'})
    
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError as ValError
    try:
        validate_password(new_password, user=user)
    except ValError as e:
        return JsonResponse({'status': 'error', 'message': e.messages[0]})

    user.set_password(new_password)
    user.save()
    
    return JsonResponse({'status': 'success', 'message': '密码修改成功，请重新登录'})


import secrets as _secrets


def _gen_code(length=6):
    return ''.join([_secrets.choice('0123456789') for _ in range(length)])


@require_http_methods(['POST'])
@csrf_protect
@rate_limit.email_code_rate_limit
def send_register_email_code(request):
    """Send a one-time code to the supplied email for registration."""
    reglink_token = request.POST.get('reglink_token', '').strip()

    if reglink_token:
        try:
            reglink = RegistrationLink.objects.get(token=reglink_token)
            if not reglink.is_valid:
                return JsonResponse(
                    {'status': 'error', 'message': '邀请链接无效或已失效'},
                    status=400
                )
        except RegistrationLink.DoesNotExist:
            return JsonResponse(
                {'status': 'error', 'message': '邀请链接不存在'},
                status=400
            )
    else:
        from apps.dashboard.models import SystemConfig
        cfg = SystemConfig.get_config()
        if not cfg.enable_registration:
            return JsonResponse(
                {'status': 'error', 'message': '注册功能已被管理员禁用'},
                status=400
            )

    email = request.POST.get('email')

    # Validate email
    if not email:
        return JsonResponse(
            {'status': 'error', 'message': '缺少email'},
            status=400
        )
    
    # 验证邮箱后缀
    from apps.dashboard.models import SystemConfig
    from django.core.cache import cache

    config = SystemConfig.get_config()

    email_suffix = '@' + email.split('@')[1] if '@' in email else ''

    cache_key = f'email_suffixes:{config.pk}'
    suffix_data = cache.get(cache_key)
    if suffix_data is None:
        whitelist = []
        if config.email_suffix_whitelist:
            whitelist = [
                s.strip()
                for s in config.email_suffix_whitelist.strip().split('\n')
                if s.strip()
            ]
        blacklist = []
        if config.email_suffix_blacklist:
            blacklist = [
                s.strip()
                for s in config.email_suffix_blacklist.strip().split('\n')
                if s.strip()
            ]
        suffix_data = {'whitelist': whitelist, 'blacklist': blacklist}
        cache.set(cache_key, suffix_data, timeout=300)

    if suffix_data['whitelist']:
        if email_suffix not in suffix_data['whitelist']:
            return JsonResponse(
                {'status': 'error',
                 'message': f'邮箱后缀 {email_suffix} 不在允许的列表中'},
                status=400
            )
    elif suffix_data['blacklist']:
        if email_suffix in suffix_data['blacklist']:
            return JsonResponse(
                {'status': 'error',
                 'message': f'邮箱后缀 {email_suffix} 已被禁止使用'},
                status=400
            )
    
    # 验证邮箱格式
    from django.core.validators import validate_email
    from django.core.exceptions import ValidationError
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse(
            {'status': 'error', 'message': '请输入有效的邮箱地址'},
            status=400
        )

    from .captcha_service import validate_captcha
    is_valid, error_msg = validate_captcha(request, scene='email')

    if not is_valid:
        return JsonResponse(
            {'status': 'error', 'message': error_msg},
            status=400
        )

    code = _gen_code(6)
    cache_key = f'register_email_code:{email}'
    cache.set(cache_key, code, timeout=10 * 60)

    subject = '2c2a 注册验证码'
    message_body = f'您的注册验证码是: {code}，有效期10分钟。'
    html_body = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6;
                color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto;
                padding: 20px; border: 1px solid #eee; }}
            .header {{ background-color: #f8f9fa; padding: 20px;
                text-align: center; border-bottom: 1px solid #dee2e6; }}
            .content {{ padding: 20px 0; }}
            .code {{ font-size: 24px; font-weight: bold; color: #007bff;
                letter-spacing: 5px; text-align: center; margin: 20px 0; }}
            .footer {{ padding: 20px 0; text-align: center;
                border-top: 1px solid #dee2e6; color: #6c757d;
                font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>2c2a 验证码服务</h2>
            </div>
            <div class="content">
                <p>您好！</p>
                <p>感谢您注册2c2a账户。</p>
                <p>您的验证码是：</p>
                <div class="code">{code}</div>
                <p>此验证码将在10分钟后失效，请及时使用。</p>
                <p>如果您没有进行相关操作，请忽略此邮件。</p>
            </div>
            <div class="footer">
                <p>© 2026 2c2a. All rights reserved.</p>
                <p>此邮件由系统自动发送，请勿回复。</p>
            </div>
        </div>
    </body>
    </html>
    '''

    from .email_service import EmailService
    try:
        EmailService.send_email_async(
            to_emails=[email],
            subject=subject,
            text_body=message_body,
            html_body=html_body,
        )
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).error(
            f'发送注册验证码邮件任务派发失败: {str(e)}',
            exc_info=True
        )
        return JsonResponse(
            {'status': 'error', 'message': 'SMTP配置不完整'},
            status=500
        )

    return JsonResponse({'status': 'ok'})


@method_decorator(rate_limit.register_rate_limit, name='dispatch')
class RegisterByLinkView(CreateView):
    model = User
    form_class = UserRegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('accounts:login')

    def dispatch(self, request, *args, **kwargs):
        token = kwargs.get('token')
        try:
            self.reglink = RegistrationLink.objects.select_related(
                'group'
            ).get(token=token)
        except RegistrationLink.DoesNotExist:
            messages.error(request, '注册链接不存在')
            return redirect('accounts:register')

        if self.reglink.is_exhausted:
            messages.error(request, '此注册链接可用次数已用完')
            return redirect('accounts:register')

        if self.reglink.is_expired:
            messages.error(request, '此注册链接已过期')
            return redirect('accounts:register')

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['reglink'] = self.reglink
        context['target_group'] = self.reglink.group
        context.update(get_captcha_context('email'))
        context.update(get_theme_context())
        return context

    def form_valid(self, form):
        import hmac
        email = form.cleaned_data.get('email')
        email_code = self.request.POST.get('email_code')
        if not (email and email_code):
            form.add_error(None, '邮箱验证码缺失')
            return self.form_invalid(form)

        cache_key = f'register_email_code:{email}'
        expected = cache.get(cache_key)
        if expected is None:
            form.add_error(None, '邮箱验证码已过期或不存在')
            return self.form_invalid(form)
        if not hmac.compare_digest(str(expected), str(email_code)):
            form.add_error(None, '邮箱验证码错误')
            return self.form_invalid(form)

        cache.delete(cache_key)

        user = form.save()

        user.groups.set([self.reglink.group])
        user.sync_staff_status()

        self.reglink.increment_usage(user)

        messages.success(
            self.request,
            f'注册成功！您已加入「{self.reglink.group.name}」组，请登录。'
        )
        return redirect(self.success_url)

    def form_invalid(self, form):
        messages.error(
            self.request,
            '注册失败，请检查表单中的错误。'
        )
        return super().form_invalid(form)


@login_required
@require_http_methods(["POST"])
@rate_limit.avatar_upload_rate_limit
def upload_avatar(request):
    """上传头像"""
    if request.method == 'POST' and request.FILES.get('avatar'):
        avatar_file = request.FILES['avatar']
        user = request.user
        
        # 验证文件扩展名
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.gif']
        ext = os.path.splitext(avatar_file.name)[1].lower()
        if ext not in allowed_extensions:
            return JsonResponse({'status': 'error', 'message': '不支持的图片格式'})
        
        # 验证文件大小 (5MB)
        if avatar_file.size > 5 * 1024 * 1024:
            return JsonResponse({'status': 'error', 'message': '图片大小不能超过5MB'})
        
        try:
            # 验证文件确实是图像文件，并检查是否包含恶意内容
            image = Image.open(avatar_file)
            image.verify()  # 验证图像完整性
            
            # 重新打开文件，因为verify()会将指针移到末尾
            avatar_file.seek(0)
            
            # 再次打开图像用于尺寸检查
            image = Image.open(avatar_file)
            
            # 检查图像尺寸是否合理（防止像素炸弹）
            max_width, max_height = 5000, 5000  # 最大允许尺寸
            if image.width > max_width or image.height > max_height:
                return JsonResponse({'status': 'error', 'message': '图片尺寸过大'})
            
            # 限制最小图像尺寸
            min_width, min_height = 10, 10
            if image.width < min_width or image.height < min_height:
                return JsonResponse({'status': 'error', 'message': '图片尺寸过小'})
            
        except Exception:
            return JsonResponse({'status': 'error', 'message': '上传的文件不是有效的图片'})
        
        # 重置文件指针以供保存
        avatar_file.seek(0)
        
        # 保存头像
        user.avatar = avatar_file
        user.save()
        
        return JsonResponse({'status': 'success', 'message': '头像上传成功'})
    
    return JsonResponse({'status': 'error', 'message': '没有上传文件'})


@method_decorator(rate_limit.register_rate_limit, name='dispatch')
class ForgotPasswordView(TemplateView):
    """忘记密码视图"""
    
    template_name = 'accounts/forgot_password.html'

    def get_context_data(self, **kwargs):
        """获取模板上下文数据"""
        context = super().get_context_data(**kwargs)
        context.update(get_captcha_context('email'))
        context.update(get_theme_context())
        return context

    def post(self, request, *args, **kwargs):
        """处理POST请求"""
        email = request.POST.get('email')
        email_code = request.POST.get('email_code')
        new_password1 = request.POST.get('new_password1')
        new_password2 = request.POST.get('new_password2')
        
        # 验证输入
        if not (email and email_code and new_password1 and new_password2):
            messages.error(request, '请填写所有必需字段')
            return self.render_to_response(self.get_context_data())

        # 1. 行为验证码
        from .captcha_service import validate_captcha
        is_valid, error_msg = validate_captcha(request, scene='email')
        if not is_valid:
            messages.error(request, error_msg)
            return self.render_to_response(self.get_context_data())

        # 2. 邮箱验证码
        import hmac
        cache_key = f'forgot_password_email_code:{email}'
        expected = cache.get(cache_key)
        if expected is None:
            messages.error(request, '邮箱验证码已过期或不存在')
            return self.render_to_response(self.get_context_data())
        if not hmac.compare_digest(str(expected), str(email_code)):
            messages.error(request, '邮箱验证码错误')
            return self.render_to_response(self.get_context_data())

        # 3. 用户存在性检查
        user_exists = User.objects.filter(email=email).exists()
        if not user_exists:
            messages.success(request, '如果该邮箱已注册，密码重置邮件已发送')
            return redirect('accounts:login')

        # 4. 密码重置
        if new_password1 != new_password2:
            messages.error(request, '两次输入的密码不一致')
            return self.render_to_response(self.get_context_data())
        
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError as ValError
        try:
            validate_password(new_password1)
        except ValError as e:
            messages.error(request, e.messages[0])
            return self.render_to_response(self.get_context_data())
        
        user = User.objects.get(email=email)
        user.set_password(new_password1)
        user.save()
        
        # 清除验证码缓存
        cache.delete(cache_key)
        
        messages.success(request, '密码重置成功，请使用新密码登录')
        return redirect('accounts:login')


@require_http_methods(['POST'])
@csrf_protect
@rate_limit.email_code_rate_limit
def send_forgot_password_email_code(request):
    """Send a one-time code to the supplied email for password reset."""
    email = request.POST.get('email')

    if not email:
        return JsonResponse(
            {'status': 'error', 'message': '缺少email'},
            status=400
        )

    from .captcha_service import validate_captcha
    is_valid, error_msg = validate_captcha(request, scene='email')

    if not is_valid:
        return JsonResponse(
            {'status': 'error', 'message': error_msg},
            status=400
        )

    user_exists = User.objects.filter(email=email).exists()

    if not user_exists:
        return JsonResponse({'status': 'ok'})

    code = _gen_code(6)
    cache_key = f'forgot_password_email_code:{email}'
    cache.set(cache_key, code, timeout=10 * 60)

    import os
    if os.environ.get('2C2A_DEMO', '').lower() == '1':
        import logging as _logging
        _logging.getLogger(__name__).info(
            f'DEMO模式: 模拟发送忘记密码验证码邮件至 {email}'
        )
        return JsonResponse({'status': 'ok'})

    subject = '2c2a 重置密码验证码'
    message_body = f'您的重置密码验证码是: {code}，有效期10分钟。'
    html_body = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6;
                color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto;
                padding: 20px; border: 1px solid #eee; }}
            .header {{ background-color: #f8f9fa; padding: 20px;
                text-align: center; border-bottom: 1px solid #dee2e6; }}
            .content {{ padding: 20px 0; }}
            .code {{ font-size: 24px; font-weight: bold; color: #007bff;
                letter-spacing: 5px; text-align: center; margin: 20px 0; }}
            .footer {{ padding: 20px 0; text-align: center;
                border-top: 1px solid #dee2e6; color: #6c757d;
                font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>2c2a 验证码服务</h2>
            </div>
            <div class="content">
                <p>您好！</p>
                <p>您正在重置2c2a账户的密码。</p>
                <p>您的验证码是：</p>
                <div class="code">{code}</div>
                <p>此验证码将在10分钟后失效，请及时使用。</p>
                <p>如果您没有进行相关操作，请忽略此邮件。</p>
            </div>
            <div class="footer">
                <p>© 2026 2c2a. All rights reserved.</p>
                <p>此邮件由系统自动发送，请勿回复。</p>
            </div>
        </div>
    </body>
    </html>
    '''

    from .email_service import EmailService
    try:
        EmailService.send_email_async(
            to_emails=[email],
            subject=subject,
            text_body=message_body,
            html_body=html_body,
        )
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).error(
            f'发送忘记密码验证码邮件任务派发失败: {str(e)}',
            exc_info=True
        )
        return JsonResponse(
            {'status': 'error', 'message': 'SMTP配置不完整'},
            status=500
        )

    return JsonResponse({'status': 'ok'})
