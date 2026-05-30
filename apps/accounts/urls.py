from django.urls import path
from django.views.decorators.cache import never_cache
from . import views

app_name = 'accounts'

urlpatterns = [
    path('register/', views.RegisterView.as_view(), name='register'),
    path('register/<str:token>/', views.RegisterByLinkView.as_view(), name='register_by_link'),
    path('login/', never_cache(views.LoginView.as_view()), name='login'),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('logout/', views.logout_view, name='logout'),
    path('email/send-code/', views.send_register_email_code, name='send_register_email_code'),
    path('forgot-password/', views.ForgotPasswordView.as_view(), name='forgot_password'),
    path('email/send-forgot-password-code/', views.send_forgot_password_email_code, name='send_forgot_password_email_code'),
    path('api/profile/avatar/', views.upload_avatar, name='upload_avatar'),
    path('api/password/change/', views.password_change_api, name='password_change_api'),
]
