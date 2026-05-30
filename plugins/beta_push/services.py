import logging
import os
from collections import OrderedDict

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connections, models, IntegrityError
from django.utils import timezone

import redis as redis_lib

User = get_user_model()
logger = logging.getLogger(__name__)

BETA_DB = 'beta'

REDIS_KEY_PREFIX = 'beta_push:progress'

ENCRYPTED_FIELDS = {
    'hosts.Host._password',
    'operations.CloudComputerUser._initial_password',
}


def _get_redis():
    url = getattr(settings, 'REDIS_URL', '')
    if not url:
        return None
    try:
        client = redis_lib.Redis.from_url(url, socket_connect_timeout=3)
        client.ping()
        return client
    except Exception:
        return None


def set_progress(task_id, current, total, message=''):
    r = _get_redis()
    if not r:
        return
    import json
    r.setex(
        f'{REDIS_KEY_PREFIX}:{task_id}',
        3600,
        json.dumps({
            'current': current,
            'total': total,
            'message': message,
        }),
    )


def get_progress(task_id):
    r = _get_redis()
    if not r:
        return None
    import json
    data = r.get(f'{REDIS_KEY_PREFIX}:{task_id}')
    if data:
        return json.loads(data)
    return None


def _get_fernet(secret_key):
    try:
        from cryptography.fernet import Fernet
        import base64
        import hashlib
        key = hashlib.sha256(secret_key.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(key))
    except ImportError:
        return None


def _re_encrypt_value(encrypted_value, model_label, field_name):
    beta_secret_key = os.environ.get('BETA_SECRET_KEY', '')
    if not beta_secret_key or not encrypted_value:
        return encrypted_value

    field_key = f'{model_label}.{field_name}'
    if field_key not in ENCRYPTED_FIELDS:
        return encrypted_value

    prod_fernet = _get_fernet(settings.SECRET_KEY)
    beta_fernet = _get_fernet(beta_secret_key)
    if not prod_fernet or not beta_fernet:
        return encrypted_value

    try:
        plaintext = prod_fernet.decrypt(encrypted_value.encode()).decode()
        return beta_fernet.encrypt(plaintext.encode()).decode()
    except Exception as e:
        logger.warning(f'重加密失败 [{field_key}]: {e}')
        return encrypted_value


class BetaPushService:
    _beta_schema_cache = {}

    def __init__(self, user_id, task_id=''):
        self.user_id = user_id
        self.user = User.objects.get(pk=user_id)
        self.task_id = task_id
        self.stats = {
            'pushed': 0,
            'skipped': 0,
            'failed': 0,
            'errors': [],
        }
        self._synced_pks = {}
        self._missing_tables = set()
        self.last_sync_at = self._get_last_sync_at()

    def _get_last_sync_at(self):
        from .models import SyncLog
        try:
            log = SyncLog.objects.filter(
                user_id=self.user_id,
                status='success',
            ).latest('completed_at')
            return log.completed_at
        except SyncLog.DoesNotExist:
            return None

    def push_all(self):
        self.__class__._beta_schema_cache.clear()

        steps = [
            ('用户信息', self._push_user),
            ('用户资料', self._push_user_profile),
            ('用户组', self._push_user_groups),
            ('主机', self._push_hosts),
            ('主机组', self._push_host_groups),
            ('产品组', self._push_product_groups),
            ('产品', self._push_products),
            ('云电脑用户', self._push_cloud_computer_users),
            ('开户申请', self._push_account_opening_requests),
            ('邀请令牌', self._push_invitation_tokens),
            ('授权记录', self._push_access_grants),
            ('域名路由', self._push_rdp_domain_routes),
        ]
        total_steps = len(steps)
        for idx, (label, step_func) in enumerate(steps, 1):
            if self.task_id:
                set_progress(self.task_id, idx, total_steps, label)
            try:
                step_func()
            except Exception as e:
                logger.error(f'Beta推送步骤失败 [{label}]: {e}', exc_info=True)
                self.stats['errors'].append(f'{label}: {str(e)}')

        if self.task_id:
            set_progress(self.task_id, total_steps, total_steps, '完成')

        return self.stats

    def _is_changed(self, instance):
        if self.last_sync_at is None:
            return True
        updated_at = getattr(instance, 'updated_at', None)
        if updated_at and updated_at > self.last_sync_at:
            return True
        created_at = getattr(instance, 'created_at', None)
        if created_at and created_at > self.last_sync_at:
            return True
        return False

    def _get_beta_table_info(self, model):
        table_name = model._meta.db_table
        if table_name in self._beta_schema_cache:
            return self._beta_schema_cache[table_name]

        info = {'exists': False, 'columns': set(), 'not_null_no_default': set()}

        try:
            with connections[BETA_DB].cursor() as cursor:
                cursor.execute(
                    "SELECT column_name, is_nullable, column_default "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s",
                    [table_name]
                )
                rows = cursor.fetchall()

                if rows:
                    info['exists'] = True
                    for col_name, is_nullable, col_default in rows:
                        info['columns'].add(col_name)
                        if is_nullable == 'NO' and col_default is None:
                            info['not_null_no_default'].add(col_name)
        except Exception as e:
            logger.error(f'查询Beta数据库表结构失败 [{table_name}]: {e}')

        self._beta_schema_cache[table_name] = info
        return info

    def _sync_instance(self, instance):
        model = instance.__class__
        model_label = f'{model._meta.app_label}.{model.__name__}'
        pk = instance.pk

        if model_label in self._synced_pks and pk in self._synced_pks[model_label]:
            self.stats['skipped'] += 1
            return True

        table_info = self._get_beta_table_info(model)
        if not table_info['exists']:
            if model._meta.db_table not in self._missing_tables:
                self.stats['errors'].append(
                    f'{model.__name__}: Beta数据库中表 {model._meta.db_table} 不存在，已跳过'
                )
                self._missing_tables.add(model._meta.db_table)
            self._synced_pks.setdefault(model_label, set()).add(pk)
            self.stats['skipped'] += 1
            return True

        if not self._is_changed(instance):
            if model.objects.using(BETA_DB).filter(pk=pk).exists():
                self._synced_pks.setdefault(model_label, set()).add(pk)
                self.stats['skipped'] += 1
                return True

        beta_columns = table_info['columns']
        field_values = {}
        m2m_values = OrderedDict()

        for field in model._meta.get_fields():
            if field.many_to_many:
                if field.auto_created:
                    continue
                m2m_values[field.name] = list(
                    getattr(instance, field.name).values_list('pk', flat=True)
                )
                continue

            if field.auto_created and not field.concrete:
                continue

            if not hasattr(instance, field.attname):
                continue

            if not hasattr(field, 'column') or field.column not in beta_columns:
                continue

            value = getattr(instance, field.attname)

            if isinstance(field, models.ForeignKey):
                if value is not None:
                    try:
                        related_obj = getattr(instance, field.name)
                        if related_obj is not None:
                            self._ensure_stub_exists(related_obj)
                    except Exception:
                        pass

            value = _re_encrypt_value(value, model_label, field.name)

            field_values[field.name] = value

        try:
            obj, created = model.objects.using(BETA_DB).update_or_create(
                pk=pk,
                defaults=field_values,
            )
        except IntegrityError as e:
            logger.warning(f'IntegrityError [{model.__name__}:{pk}]: {e}')
            if model.objects.using(BETA_DB).filter(pk=pk).exists():
                try:
                    model.objects.using(BETA_DB).filter(pk=pk).update(**field_values)
                    obj = model.objects.using(BETA_DB).get(pk=pk)
                except Exception as e2:
                    self.stats['failed'] += 1
                    self.stats['errors'].append(
                        f'{model.__name__}:{pk} - 更新失败: {str(e2)}'
                    )
                    return False
            else:
                prod_cols = {
                    f.column for f in model._meta.concrete_fields if hasattr(f, 'column')
                }
                missing = table_info['not_null_no_default'] - prod_cols
                hint = (
                    f'Beta数据库存在额外NOT NULL无默认值列: {missing}'
                    if missing else str(e)
                )
                self.stats['failed'] += 1
                self.stats['errors'].append(
                    f'{model.__name__}:{pk} - 创建失败: {hint}'
                )
                return False

        for field_name, related_pks in m2m_values.items():
            try:
                m2m_field = model._meta.get_field(field_name)
                m2m_through_info = self._get_beta_table_info(
                    m2m_field.remote_field.through
                )
                if not m2m_through_info['exists']:
                    logger.warning(
                        f'M2M中间表不存在于Beta数据库 [{model.__name__}.{field_name}]'
                    )
                    continue

                m2m_model = m2m_field.related_model
                existing_pks = set(
                    m2m_model.objects.using(BETA_DB).filter(
                        pk__in=related_pks
                    ).values_list('pk', flat=True)
                )
                m2m_manager = getattr(obj, field_name)
                m2m_manager.set(existing_pks)
            except Exception as e:
                logger.warning(f'M2M同步失败 [{model.__name__}.{field_name}]: {e}')

        self._synced_pks.setdefault(model_label, set()).add(pk)
        self.stats['pushed'] += 1
        return True

    def _ensure_stub_exists(self, related_instance):
        model = related_instance.__class__
        model_label = f'{model._meta.app_label}.{model.__name__}'
        pk = related_instance.pk

        if model._meta.db_table in self._missing_tables:
            return

        if model_label in self._synced_pks and pk in self._synced_pks[model_label]:
            return

        if model.objects.using(BETA_DB).filter(pk=pk).exists():
            self._synced_pks.setdefault(model_label, set()).add(pk)
            return

        self._sync_instance(related_instance)

    def _push_user(self):
        self._sync_instance(self.user)

    def _push_user_profile(self):
        try:
            profile = self.user.profile
            self._sync_instance(profile)
        except Exception:
            pass

    def _push_user_groups(self):
        for group in self.user.groups.all():
            try:
                if not group.__class__.objects.using(BETA_DB).filter(pk=group.pk).exists():
                    self._sync_instance(group)
                try:
                    gp = group.profile
                    self._sync_instance(gp)
                except Exception:
                    pass
            except Exception:
                pass

    def _get_provider_hosts(self):
        from apps.hosts.models import Host
        if self.user.is_superuser:
            return Host.objects.all()
        return Host.objects.filter(providers=self.user)

    def _push_hosts(self):
        from apps.hosts.models import Host
        hosts = self._get_provider_hosts()
        for host in hosts:
            self._sync_instance(host)

    def _get_provider_host_groups(self):
        from apps.hosts.models import HostGroup
        if self.user.is_superuser:
            return HostGroup.objects.all()
        return HostGroup.objects.filter(providers=self.user)

    def _push_host_groups(self):
        from apps.hosts.models import HostGroup
        host_groups = self._get_provider_host_groups()
        for hg in host_groups:
            self._sync_instance(hg)

    def _get_provider_product_groups(self):
        from apps.operations.models import ProductGroup
        if self.user.is_superuser:
            return ProductGroup.objects.all()
        return ProductGroup.objects.filter(created_by=self.user)

    def _push_product_groups(self):
        from apps.operations.models import ProductGroup
        product_groups = self._get_provider_product_groups()
        for pg in product_groups:
            self._sync_instance(pg)

    def _get_provider_products(self):
        from apps.operations.models import Product
        if self.user.is_superuser:
            return Product.objects.all()
        return Product.objects.filter(created_by=self.user)

    def _push_products(self):
        from apps.operations.models import Product
        products = self._get_provider_products()
        for product in products:
            self._sync_instance(product)

    def _get_provider_cloud_users(self):
        from apps.operations.models import CloudComputerUser, Product
        if self.user.is_superuser:
            return CloudComputerUser.objects.all()
        provider_product_ids = Product.objects.filter(
            created_by=self.user
        ).values_list('pk', flat=True)
        return CloudComputerUser.objects.filter(product_id__in=provider_product_ids)

    def _push_cloud_computer_users(self):
        from apps.operations.models import CloudComputerUser
        cloud_users = self._get_provider_cloud_users()
        for cu in cloud_users:
            self._sync_instance(cu)

    def _get_provider_requests(self):
        from apps.operations.models import AccountOpeningRequest, Product
        if self.user.is_superuser:
            return AccountOpeningRequest.objects.all()
        provider_product_ids = Product.objects.filter(
            created_by=self.user
        ).values_list('pk', flat=True)
        return AccountOpeningRequest.objects.filter(
            target_product_id__in=provider_product_ids
        )

    def _push_account_opening_requests(self):
        from apps.operations.models import AccountOpeningRequest
        requests = self._get_provider_requests()
        for req in requests:
            self._sync_instance(req)

    def _get_provider_invitation_tokens(self):
        from apps.operations.models import ProductInvitationToken
        if self.user.is_superuser:
            return ProductInvitationToken.objects.all()
        return ProductInvitationToken.objects.filter(created_by=self.user)

    def _push_invitation_tokens(self):
        from apps.operations.models import ProductInvitationToken
        tokens = self._get_provider_invitation_tokens()
        for token in tokens:
            self._sync_instance(token)

    def _get_provider_access_grants(self):
        from apps.operations.models import ProductAccessGrant, Product
        if self.user.is_superuser:
            return ProductAccessGrant.objects.all()
        provider_product_ids = Product.objects.filter(
            created_by=self.user
        ).values_list('pk', flat=True)
        return ProductAccessGrant.objects.filter(
            product_id__in=provider_product_ids
        )

    def _push_access_grants(self):
        from apps.operations.models import ProductAccessGrant
        grants = self._get_provider_access_grants()
        for grant in grants:
            self._sync_instance(grant)

    def _get_provider_rdp_routes(self):
        from apps.operations.models import RdpDomainRoute, Product
        if self.user.is_superuser:
            return RdpDomainRoute.objects.all()
        provider_product_ids = Product.objects.filter(
            created_by=self.user
        ).values_list('pk', flat=True)
        return RdpDomainRoute.objects.filter(product_id__in=provider_product_ids)

    def _push_rdp_domain_routes(self):
        from apps.operations.models import RdpDomainRoute
        routes = self._get_provider_rdp_routes()
        for route in routes:
            self._sync_instance(route)
