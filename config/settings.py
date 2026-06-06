"""
Django settings for 2c2a project.

配置加载优先级（从高到低）：
1. 环境变量（os.environ）- 方便 DEMO 配置和容器部署
2. .env 文件 - 本地开发配置
3. 默认值 - 确保基本可用

DEMO 模式（2C2A_DEMO=1）会强制锁定特定配置，不受 .env 影响。
"""

import os
import importlib
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# ========== .env 文件加载 ==========
# 优先级：环境变量 > .env 文件 > 默认值
# 使用 python-dotenv 加载 .env，但不覆盖已存在的环境变量
from dotenv import load_dotenv

ENV_FILE = BASE_DIR / '.env'
if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE, override=False)


def _env(key, default=None):
    """
    读取配置的统一入口。
    优先级：环境变量 > .env 文件 > 默认值
    """
    return os.environ.get(key, default)


# ========== 核心配置（必须在初始化时定义） ==========

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DB_ENGINE = _env('DB_ENGINE', 'sqlite').lower()

if DB_ENGINE == 'mysql':
    import pymysql
    pymysql.install_as_MySQLdb()

    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': _env('DB_NAME', '2c2a'),
            'USER': _env('DB_USER', 'root'),
            'PASSWORD': _env('DB_PASSWORD', ''),
            'HOST': _env('DB_HOST', '127.0.0.1'),
            'PORT': _env('DB_PORT', '3306'),
            'CONN_MAX_AGE': int(_env('DB_CONN_MAX_AGE', '60')),
            'OPTIONS': {
                'charset': 'utf8mb4',
                'init_command': (
                    "SET sql_mode='STRICT_TRANS_TABLES'"
                ),
            },
        }
    }
elif DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': _env('DB_NAME', '2c2a'),
            'USER': _env('DB_USER', 'postgres'),
            'PASSWORD': _env('DB_PASSWORD', ''),
            'HOST': _env('DB_HOST', '127.0.0.1'),
            'PORT': _env('DB_PORT', '5432'),
            'CONN_MAX_AGE': int(_env('DB_CONN_MAX_AGE', '60')),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# SECURITY WARNING: keep the secret key used in production secret!
_INSECURE_SECRET_KEY = 'django-insecure-change-this-in-production'
SECRET_KEY = _env('DJANGO_SECRET_KEY', _INSECURE_SECRET_KEY)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = _env('DEBUG', 'False').lower() == 'true'

if SECRET_KEY == _INSECURE_SECRET_KEY and not DEBUG:
    raise ImproperlyConfigured(
        'DJANGO_SECRET_KEY 环境变量必须设置，不允许在生产环境使用默认不安全密钥'
    )

# 允许的主机列表
# 在DEBUG模式下，允许所有主机
if DEBUG:
    ALLOWED_HOSTS = _env('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost',
        'http://127.0.0.1',
        'https://localhost',
        'https://127.0.0.1',
        'https://demo.supercmd.dpdns.org',
        'https://2c2a.supercmd.dpdns.org',
    ]
else:
    ALLOWED_HOSTS = _env('ALLOWED_HOSTS', '').split(',')
    CSRF_TRUSTED_ORIGINS = _env('CSRF_TRUSTED_ORIGINS', 'https://localhost,https://127.0.0.1').split(',')
    _ALLOWED_HOSTS_ENV = _env('ALLOWED_HOSTS', '')
    if not _ALLOWED_HOSTS_ENV or _ALLOWED_HOSTS_ENV == 'localhost,127.0.0.1':
        raise ImproperlyConfigured(
            'ALLOWED_HOSTS 环境变量必须在生产环境中显式配置为实际域名'
        )

# Application definition

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # 第三方应用
    'rest_framework',
    'corsheaders',

    # 模板组件框架（必须在本地应用之前，确保 cotton 模板优先发现）
    'django_cotton',

    # 本地应用
    'django_tianai_captcha',

    'apps.accounts',
    'apps.hosts',
    'apps.operations',
    'apps.dashboard',
    'apps.certificates',
    'apps.bootstrap',  # 主机引导系统
    'apps.audit',
    'apps.tasks',
    'apps.themes',  # 主题系统
    'apps.tunnel',  # 隧道管理
    'apps.tickets',  # 工单系统
    'apps.provider',  # 提供商后台（新版 Tailwind/MD3）
    'apps.provider_backend',  # 提供商后台（旧版，保留中间件和API）
    'plugins',
]

# ========== 插件 Django App 动态注册 ==========
# 从 plugins.toml 读取需要注册为 Django App 的插件模块
# 这样插件不存在时系统仍能正常启动（松耦合）
def _discover_plugin_apps():
    plugin_apps = []
    seen = set()
    toml_path = BASE_DIR / 'plugins' / 'plugins.toml'
    if not toml_path.exists():
        return plugin_apps
    try:
        import toml
        toml_data = toml.loads(toml_path.read_text(encoding='utf-8'))
        for section in ('builtin', 'third_party'):
            for _key, info in toml_data.get(section, {}).items():
                if not info.get('enabled', True):
                    continue
                if not info.get('django_app', True):
                    continue
                module = info.get('module', '')
                if not module:
                    continue
                parts = module.split('.')
                if len(parts) >= 2 and parts[0] == 'plugins':
                    app_module = '.'.join(parts[:2])
                else:
                    app_module = module
                if app_module in seen:
                    continue
                seen.add(app_module)
                pkg_dir = (
                    BASE_DIR / 'plugins' / app_module.split('.')[-1]
                )
                if pkg_dir.is_dir() and (pkg_dir / '__init__.py').exists():
                    plugin_apps.append(app_module)
    except Exception:
        pass
    return plugin_apps

INSTALLED_APPS += _discover_plugin_apps()

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'config.maintenance_middleware.MaintenanceModeMiddleware',
    'config.local_lock_middleware.LocalLockMiddleware',
    'config.security_middleware.SecurityHeadersMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.dashboard.middleware.SiteGroupMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'apps.bootstrap.middleware.SessionValidationMiddleware',
    'config.demo_middleware.DemoModeMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            BASE_DIR / 'templates',
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.dashboard.context_processors.system_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = 'zh-hans'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

# Media files
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
    },
}

# CORS settings
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in _env(
        'CORS_ALLOWED_ORIGINS',
        'http://localhost:8000,https://localhost,http://127.0.0.1:8000'
    ).split(',')
    if origin.strip()
]


# Winrm settings
WINRM_TIMEOUT = int(_env('WINRM_TIMEOUT', '30'))  # Winrm连接超时时间（秒）
WINRM_MAX_RETRIES = int(_env('WINRM_RETRY_COUNT', '3'))  # Winrm连接最大重试次数

# Logging settings
# 默认只输出到 stdout，方便 nohup/systemd 等收集日志
# 如需文件日志，设置环境变量 LOG_FILE=/path/to/2c2a.log
LOG_LEVEL = _env('LOG_LEVEL', 'INFO')
LOG_FILE = _env('LOG_FILE', '')

_logging_handlers = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
    },
}
_logging_root_handlers = ['console']
_logging_logger_handlers = ['console']

if LOG_FILE:
    _logging_handlers['file'] = {
        'class': 'logging.handlers.RotatingFileHandler',
        'filename': LOG_FILE,
        'maxBytes': 1024 * 1024 * 10,  # 10MB
        'backupCount': 5,
        'formatter': 'verbose',
    }
    _logging_root_handlers.append('file')
    _logging_logger_handlers.append('file')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': _logging_handlers,
    'root': {
        'handlers': _logging_root_handlers,
        'level': LOG_LEVEL,
    },
    'loggers': {
        'django': {
            'handlers': _logging_logger_handlers,
            'level': LOG_LEVEL,
            'propagate': False,
        },
        '2c2a': {
            'handlers': _logging_logger_handlers,
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}

# 安全配置
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

SECURE_CROSS_ORIGIN_OPENER_POLICY = 'same-origin'

if not DEBUG:
    SECURE_CROSS_ORIGIN_EMBEDDER_POLICY = 'require-corp'
    SECURE_CROSS_ORIGIN_RESOURCE_POLICY = 'same-origin'

USE_X_FORWARDED_FOR = _env(
    'USE_X_FORWARDED_FOR', 'False'
).lower() == 'true'

# 可信反向代理 IP 集合（nginx 等）
# 当 REMOTE_ADDR 在此集合中时，从 X-Forwarded-For / X-Real-IP 获取真实客户端 IP
# 防止代理场景下所有用户共享同一 IP 导致限流误触发
TRUSTED_PROXY_IPS = set(
    _env('TRUSTED_PROXY_IPS', '127.0.0.1,::1').split(',')
)

SESSION_COOKIE_SECURE = _env(
    'SESSION_COOKIE_SECURE', 'True' if not DEBUG else 'False'
).lower() == 'true'
CSRF_COOKIE_SECURE = _env(
    'CSRF_COOKIE_SECURE', 'True' if not DEBUG else 'False'
).lower() == 'true'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = int(_env('SESSION_COOKIE_AGE', '3600'))
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# HTTPS相关安全配置 (仅在生产环境中启用)
if not DEBUG:
    SECURE_SSL_REDIRECT = _env('SECURE_SSL_REDIRECT', 'True').lower() == 'true'
    SECURE_HSTS_SECONDS = 31536000  # 一年
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ========== Redis 可选配置 ==========
# Redis 是锦上添花的增强组件，不配置时程序使用本地替代方案。
# 配置 REDIS_URL 且 Redis 服务可达时，自动用于缓存、会话、Celery。
# import redis 采用延迟导入：REDIS_URL 未配置时不 import，redis 包未安装也不报错。
REDIS_URL = _env('REDIS_URL', '')

def _check_redis_available():
    """检测 Redis 是否配置且可达（延迟导入 redis 包）"""
    if not REDIS_URL:
        return False
    try:
        import redis as _redis
        client = _redis.Redis.from_url(REDIS_URL, socket_connect_timeout=3)
        client.ping()
        return True
    except Exception:
        return False

REDIS_ENABLED = _check_redis_available()

# ========== 缓存配置 ==========
if REDIS_ENABLED:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'KEY_PREFIX': '2c2a',
            'TIMEOUT': 300,
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': '2c2a-inmemory',
            'KEY_PREFIX': '2c2a',
            'TIMEOUT': 300,
            'OPTIONS': {
                'MAX_ENTRIES': 1000,
            },
        },
    }

# ========== 会话引擎 ==========
if REDIS_ENABLED:
    SESSION_ENGINE = 'django.contrib.sessions.backends.cache'
    SESSION_CACHE_ALIAS = 'default'
else:
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'

# ========== Celery 配置 ==========
if REDIS_ENABLED:
    CELERY_BROKER_URL = _env(
        'CELERY_BROKER_URL',
        REDIS_URL.replace('/0', '/1') if REDIS_URL else 'redis://localhost:6379/1',
    )
    CELERY_RESULT_BACKEND = _env(
        'CELERY_RESULT_BACKEND',
        REDIS_URL.replace('/0', '/2') if REDIS_URL else 'redis://localhost:6379/2',
    )
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        'polling_interval': 1,
        'max_connections': 20,
    }
else:
    CELERY_BROKER_URL = f'sqla+sqlite:///{BASE_DIR / "celery_broker.sqlite3"}'
    CELERY_RESULT_BACKEND = f'db+sqlite:///{BASE_DIR / "celery_results.sqlite3"}'
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        'polling_interval': 1,
    }

# ========== 限流配置 ==========
LOGIN_RATE_LIMIT = int(_env('LOGIN_RATE_LIMIT', '5'))
API_RATE_LIMIT = int(_env('API_RATE_LIMIT', '100'))

# Gateway 控制面配置
GATEWAY_ENABLED = _env(
    'GATEWAY_ENABLED', 'False'
).lower() in ('true', '1', 'yes')
GATEWAY_CONTROL_SOCKET = _env(
    'GATEWAY_CONTROL_SOCKET', '/run/2c2a/control.sock'
)

GATEWAY_PAA_TOKEN_SIGNING_KEY = _env(
    'GATEWAY_PAA_TOKEN_SIGNING_KEY', 'change-me-32-chars-minimum!!'
)

_INSECURE_GATEWAY_KEY = 'change-me-32-chars-minimum!!'
if not DEBUG and GATEWAY_ENABLED and GATEWAY_PAA_TOKEN_SIGNING_KEY == _INSECURE_GATEWAY_KEY:
    raise ImproperlyConfigured(
        'GATEWAY_PAA_TOKEN_SIGNING_KEY 环境变量必须设置，不允许在生产环境使用默认不安全密钥'
    )
GATEWAY_PAA_TOKEN_EXPIRY_SECONDS = int(_env(
    'GATEWAY_PAA_TOKEN_EXPIRY_SECONDS', '600'
))
GATEWAY_ADDRESS = _env('GATEWAY_ADDRESS', 'rdp.2c2a.com')
GATEWAY_PORT = int(_env('GATEWAY_PORT', '443'))

# RDP 域名配置
RDP_DOMAIN = _env('RDP_DOMAIN', '2c2a.com')

# ========== DEMO模式配置（强制锁定，不受 .env 影响） ==========
DEMO_MODE = os.environ.get('2C2A_DEMO', '').lower() == '1'

if DEMO_MODE:
    # DEMO模式强制使用 DEMO.sqlite3，不受 DB_ENGINE 或 .env 影响
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'DEMO.sqlite3',
        }
    }

    # DEMO模式保留最小长度验证，仅放宽复杂度要求
    AUTH_PASSWORD_VALIDATORS = [
        {
            'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
            'OPTIONS': {'min_length': 4},
        },
    ]

    ALLOWED_HOSTS = _env(
        'ALLOWED_HOSTS',
        'localhost,127.0.0.1,demo.supercmd.dpdns.org,2c2a.supercmd.dpdns.org'
    ).split(',')

    # DEBUG模式开启
    DEBUG = True

    # 生成随机SECRET_KEY（每次启动不同）
    import secrets as _secrets
    SECRET_KEY = _secrets.token_urlsafe(50)
    import logging as _logging
    _logging.getLogger('2c2a').warning('DEMO模式: 使用随机生成的SECRET_KEY，重启后所有session将失效')

# DEMO模式启动消息
if DEMO_MODE:
    from config.demo_startup import show_demo_startup_message
    show_demo_startup_message()

# Create logs directory if it doesn't exist
os.makedirs(BASE_DIR / 'logs', exist_ok=True)

# Bootstrap认证配置
BOOTSTRAP_SHARED_SALT = _env('BOOTSTRAP_SHARED_SALT', '')

if not DEBUG and not BOOTSTRAP_SHARED_SALT:
    import logging as _bootstrap_logging
    _bootstrap_logging.getLogger('2c2a').warning(
        'BOOTSTRAP_SHARED_SALT 未设置，建议在生产环境中配置此值以增强引导认证安全性'
    )

CAPTCHA = {
    "PREFIX": "captcha",
    "EXPIRE": {
        "default": 120,
        "WORD_IMAGE_CLICK": 180,
    },
    "INIT_DEFAULT_RESOURCE": True,
    "CACHE_BACKEND": "redis" if REDIS_ENABLED else "local",
    "REDIS_URL": REDIS_URL if REDIS_ENABLED else "",
    "DEFAULT_TYPE": "SLIDER",
    "TOLERANT": 0.02,
    "TRACK_VALIDATION_ENABLED": True,
    "SECONDARY": {
        "ENABLED": True,
        "EXPIRE": 120,
        "KEY_PREFIX": "captcha:secondary",
    },
    "RATE_LIMIT": {
        "ENABLED": True,
        "RATE": 10,
        "PERIOD": 60,
    },
}
