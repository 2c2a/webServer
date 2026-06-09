from django.urls import path
from django.views.decorators.cache import never_cache
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path(
        'register/<str:token>/',
        views.RegisterByLinkView.as_view(),
        name='register_by_link',
    ),
    path(
        'login/',
        never_cache(views.LoginView.as_view()),
        name='login',
    ),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('migrate/', views.migrate_view, name='migrate'),
    path('banned/', views.banned_view, name='banned'),
    path('logout/', views.logout_view, name='logout'),
    path(
        'email/send-code/',
        views.send_register_email_code,
        name='send_register_email_code',
    ),
    path(
        'forgot-password/',
        views.ForgotPasswordView.as_view(),
        name='forgot_password',
    ),
    path(
        'email/send-forgot-password-code/',
        views.send_forgot_password_email_code,
        name='send_forgot_password_email_code',
    ),
    path(
        'api/profile/avatar/',
        views.upload_avatar,
        name='upload_avatar',
    ),
    path(
        'api/password/change/',
        views.password_change_api,
        name='password_change_api',
    ),
    # 邮箱绑定 API
    path(
        'api/emails/',
        views.email_list_api,
        name='email_list',
    ),
    path(
        'api/emails/bind/',
        views.email_bind_api,
        name='email_bind',
    ),
    path(
        'api/emails/send-bind-code/',
        views.send_bind_email_code,
        name='send_bind_email_code',
    ),
    path(
        'api/emails/<int:email_id>/set-primary/',
        views.email_set_primary_api,
        name='email_set_primary',
    ),
    path(
        'api/emails/<int:email_id>/unbind/',
        views.email_unbind_api,
        name='email_unbind',
    ),
    path(
        'api/emails/merge-confirm/',
        views.email_merge_confirm_api,
        name='email_merge_confirm',
    ),
]
