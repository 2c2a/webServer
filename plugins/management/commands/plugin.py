"""
插件管理命令
提供类似 pip 的插件管理功能，支持安装、卸载、搜索、登录等操作
支持从文件安装：将插件目录解压到 plugins/ 目录后，使用 scan 发现并 install 安装
"""
import os
import sys
import subprocess
import json
import re
import toml
import inspect
import zipfile
import tempfile
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from plugins.core.plugin_manager import get_plugin_manager
from plugins.models import PluginRecord
import importlib
import importlib.util
from plugins.available_plugins import ALL_AVAILABLE_PLUGINS
import shutil
import urllib.request
import urllib.error

PLUGIN_REGISTRY_URL = "https://raw.githubusercontent.com/2c2a/2c2a-plugin-registry/main/plugins.json"
PLUGIN_REGISTRY_RAW_API = "https://api.github.com/repos/2c2a/2c2a-plugin-registry/contents/plugins.json"
PLUGIN_REGISTRY_GITEE_URL = "https://raw.giteeusercontent.com/Bilibili-Supercmd/plugin-registry/raw/main/plugins.json"


class Command(BaseCommand):
    help = '插件管理命令，类似 pip 的功能'

    def add_arguments(self, parser):
        parser.add_argument('action', type=str, help='操作类型: install, upgrade, uninstall, list, info, search, scan, login, enable, disable')
        parser.add_argument('plugin_name', nargs='?', type=str, help='插件名称、本地路径或zip文件路径')
        parser.add_argument('--source', type=str, help='插件源地址或本地路径')
        parser.add_argument('--force', action='store_true', help='强制执行操作')
        parser.add_argument('--no-migrate', action='store_true', help='跳过数据库迁移')
        parser.add_argument('--debug', action='store_true', help='输出调试信息')
        parser.add_argument('--registry', type=str, default=PLUGIN_REGISTRY_URL, help='插件仓库地址')
        parser.add_argument('--force-github', action='store_true', help='强制使用 GitHub 插件仓库')
        parser.add_argument('--force-gitee', action='store_true', help='强制使用 Gitee 插件仓库镜像')
        parser.add_argument('--install-all', action='store_true', help='与 scan 配合使用，安装所有发现的未注册插件')

    def handle(self, *args, **options):
        action = options['action']
        plugin_name = options.get('plugin_name')
        no_migrate = options.get('no_migrate', False)
        self.debug = options.get('debug', False)

        registry_url = options.get('registry')
        if options.get('force_gitee'):
            registry_url = PLUGIN_REGISTRY_GITEE_URL
        elif options.get('force_github'):
            registry_url = PLUGIN_REGISTRY_URL

        if action == 'list':
            self.list_plugins()
        elif action == 'scan':
            self.scan_plugins(
                install_all=options.get('install_all', False),
                no_migrate=no_migrate,
            )
        elif action == 'install':
            if not plugin_name:
                raise CommandError('安装插件需要指定插件名称、路径或zip文件')
            self.install_plugin(
                plugin_name,
                options.get('source'),
                options.get('force'),
                registry_url,
                no_migrate=no_migrate,
            )
        elif action == 'upgrade':
            if not plugin_name:
                raise CommandError('升级插件需要指定插件名称')
            self.upgrade_plugin(plugin_name, registry_url)
        elif action == 'uninstall':
            if not plugin_name:
                raise CommandError('卸载插件需要指定插件名称')
            self.uninstall_plugin(
                plugin_name,
                options.get('force'),
                no_migrate=no_migrate,
            )
        elif action == 'info':
            if not plugin_name:
                raise CommandError('查看插件信息需要指定插件名称')
            self.plugin_info(plugin_name)
        elif action == 'search':
            keyword = plugin_name or ''
            self.search_plugins(keyword, registry_url)
        elif action == 'login':
            self.login_github()
        elif action == 'enable':
            if not plugin_name:
                raise CommandError('启用插件需要指定插件名称')
            self.enable_plugin(plugin_name)
        elif action == 'disable':
            if not plugin_name:
                raise CommandError('禁用插件需要指定插件名称')
            self.disable_plugin(plugin_name)
        else:
            raise CommandError(
                f'未知的操作: {action}. '
                f'支持的操作: install, upgrade, uninstall, '
                f'list, info, search, scan, login, enable, disable'
            )

    def _fetch_registry(self, registry_url=None):
        url = registry_url or PLUGIN_REGISTRY_URL
        urls_to_try = []

        if url == PLUGIN_REGISTRY_GITEE_URL:
            urls_to_try = [PLUGIN_REGISTRY_GITEE_URL, PLUGIN_REGISTRY_URL]
        elif url == PLUGIN_REGISTRY_URL:
            urls_to_try = [PLUGIN_REGISTRY_URL, PLUGIN_REGISTRY_GITEE_URL]
        else:
            urls_to_try = [url, PLUGIN_REGISTRY_GITEE_URL, PLUGIN_REGISTRY_URL]

        last_error = None
        for try_url in urls_to_try:
            try:
                req = urllib.request.Request(try_url, headers={'User-Agent': '2c2a-PluginManager/1.0'})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                return data.get('plugins', {})
            except Exception as e:
                last_error = e
                continue

        try:
            result = subprocess.run(
                ['gh', 'api', '-H', 'Accept: application/vnd.github.v3.raw',
                 'repos/2c2a/2c2a-plugin-registry/contents/plugins.json'],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                return data.get('plugins', {})
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except json.JSONDecodeError:
            pass
        except Exception:
            pass

        raise CommandError(
            '无法访问插件仓库。\n'
            '请检查网络连接或使用 "uv run manage.py plugin login" 登录 GitHub CLI 后重试。'
        )

    def search_plugins(self, keyword='', registry_url=None):
        remote_plugins = self._fetch_registry(registry_url)
        if not remote_plugins:
            self.stdout.write('远程插件仓库中没有插件')
            return

        results = {}
        for plugin_id, info in remote_plugins.items():
            if not keyword:
                results[plugin_id] = info
            else:
                kw = keyword.lower()
                if (kw in plugin_id.lower() or
                    kw in info.get('name', '').lower() or
                    kw in info.get('description', '').lower()):
                    results[plugin_id] = info

        if not results:
            self.stdout.write(f'未找到与 "{keyword}" 匹配的插件')
            return

        self.stdout.write(self.style.SUCCESS(f'找到 {len(results)} 个插件:'))
        self.stdout.write('')
        for plugin_id, info in results.items():
            self.stdout.write(f'  {self.style.SUCCESS(plugin_id)}')
            self.stdout.write(f'    名称: {info.get("name", "N/A")}')
            self.stdout.write(f'    简介: {info.get("description", "N/A")}')
            self.stdout.write(f'    仓库: {info.get("repository", "N/A")}')
            self.stdout.write(f'    版本: {info.get("version", "N/A")}')
            self.stdout.write('')

    def scan_plugins(self, install_all=False, no_migrate=False):
        plugins_base = os.path.join(settings.BASE_DIR, 'plugins')
        if not os.path.isdir(plugins_base):
            raise CommandError(f'插件目录不存在: {plugins_base}')

        registered_ids = set(ALL_AVAILABLE_PLUGINS.keys())
        db_ids = set(
            PluginRecord.objects.values_list('plugin_id', flat=True)
        )
        loaded_plugins = get_plugin_manager().get_all_plugins()
        loaded_ids = set(loaded_plugins.keys())

        skip_dirs = {'core', 'management', 'templatetags', 'migrations',
                     '__pycache__', '.git'}

        discovered = []

        for entry in sorted(os.listdir(plugins_base)):
            entry_path = os.path.join(plugins_base, entry)
            if not os.path.isdir(entry_path):
                continue
            if entry in skip_dirs:
                continue
            if entry.startswith('.') or entry.startswith('_'):
                continue
            init_file = os.path.join(entry_path, '__init__.py')
            if not os.path.exists(init_file):
                continue

            has_plugin_class = self._detect_plugin_class(entry, entry_path)
            if not has_plugin_class:
                continue

            is_registered = entry in registered_ids
            is_in_db = entry in db_ids
            is_loaded = entry in loaded_ids

            if is_registered or is_in_db or is_loaded:
                continue

            plugin_class, plugin_module_name = self._load_plugin_class_from_package(
                entry, entry_path
            )
            plugin_name = entry
            plugin_version = '0.0.0'
            plugin_desc = ''
            if plugin_class:
                try:
                    inst = plugin_class()
                    plugin_name = inst.name
                    plugin_version = inst.version
                    plugin_desc = inst.description
                except Exception as exc:
                    self.stderr.write(
                        f"Warning: failed to read metadata from plugin '{entry}': {exc}"
                    )

            discovered.append({
                'dir_name': entry,
                'path': entry_path,
                'name': plugin_name,
                'version': plugin_version,
                'description': plugin_desc,
                'plugin_class': plugin_class,
                'plugin_module_name': plugin_module_name,
            })

        if not discovered:
            self.stdout.write(self.style.SUCCESS('没有发现未注册的插件'))
            return

        self.stdout.write(self.style.SUCCESS(
            f'发现 {len(discovered)} 个未注册的插件:'
        ))
        self.stdout.write('')
        for info in discovered:
            self.stdout.write(f'  {self.style.SUCCESS(info["dir_name"])}')
            self.stdout.write(f'    名称: {info["name"]}')
            self.stdout.write(f'    版本: {info["version"]}')
            self.stdout.write(f'    描述: {info["description"]}')
            self.stdout.write(f'    路径: {info["path"]}')
            self.stdout.write('')

        if install_all:
            self.stdout.write('正在安装所有发现的插件...')
            for info in discovered:
                try:
                    app_label = self._register_discovered_plugin(
                        info, no_migrate=no_migrate
                    )
                    self.stdout.write(self.style.SUCCESS(
                        f'  ✓ {info["name"]} 安装完成'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.ERROR(
                        f'  ✗ {info["dir_name"]} 安装失败: {str(e)}'
                    ))
        else:
            self.stdout.write(
                '使用 "uv run python manage.py plugin install <目录名>" '
                '安装单个插件\n'
                '使用 "uv run python manage.py plugin scan --install-all" '
                '安装所有发现的插件'
            )

    def _detect_plugin_class(self, dir_name, dir_path):
        init_file = os.path.join(dir_path, '__init__.py')
        if os.path.exists(init_file):
            try:
                with open(init_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                if re.search(
                    r'class\s+\w+\s*\([^)]*PluginInterface',
                    content, re.DOTALL
                ):
                    return True
                if 'PLUGIN_INFO' in content:
                    return True
            except Exception:
                pass

        for item in os.listdir(dir_path):
            if not item.endswith('.py') or item == '__init__.py':
                continue
            fp = os.path.join(dir_path, item)
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
                if re.search(
                    r'class\s+\w+\s*\([^)]*PluginInterface',
                    content, re.DOTALL
                ):
                    return True
            except Exception:
                continue

        return False

    def _register_discovered_plugin(self, info, no_migrate=False):
        plugin_class = info['plugin_class']
        plugin_module_name = info['plugin_module_name']
        dir_name = info['dir_name']

        if not plugin_class:
            plugin_class, plugin_module_name = self._load_plugin_class_from_package(
                dir_name, info['path']
            )

        if not plugin_class:
            raise CommandError(
                f'在 {info["path"]} 中未找到有效的插件类'
            )

        plugin_instance = plugin_class()
        plugin_manager = get_plugin_manager()
        plugin_manager.plugins[plugin_instance.plugin_id] = plugin_instance

        try:
            plugin_instance.initialize()
        except Exception:
            pass

        PluginRecord.objects.update_or_create(
            plugin_id=plugin_instance.plugin_id,
            defaults={
                'name': plugin_instance.name,
                'version': plugin_instance.version,
                'description': plugin_instance.description,
                'is_active': True,
            }
        )

        self.add_plugin_to_toml_config(plugin_instance.plugin_id, {
            'name': plugin_instance.name,
            'module': plugin_module_name,
            'class': plugin_class.__name__,
            'description': plugin_instance.description,
            'version': plugin_instance.version,
            'enabled': True
        })

        app_label = self._get_app_label_from_module(plugin_module_name)
        if app_label and not no_migrate:
            self._run_migrate(app_label)

        return app_label

    def login_github(self):
        self.stdout.write('正在检查 GitHub CLI 认证状态...')
        try:
            result = subprocess.run(
                ['gh', 'auth', 'status'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS('GitHub CLI 已认证'))
                self.stdout.write(result.stdout.strip())
                return
        except FileNotFoundError:
            raise CommandError(
                '未找到 gh CLI，请先安装 GitHub CLI: https://cli.github.com/'
            )
        except subprocess.TimeoutExpired:
            raise CommandError('检查认证状态超时')

        self.stdout.write('GitHub CLI 未认证，正在启动登录流程...')
        try:
            result = subprocess.run(
                ['gh', 'auth', 'login'],
                stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS('GitHub 登录成功!'))
            else:
                raise CommandError('GitHub 登录失败')
        except FileNotFoundError:
            raise CommandError(
                '未找到 gh CLI，请先安装 GitHub CLI: https://cli.github.com/'
            )

    def install_plugin(self, plugin_name, source=None, force=False, registry_url=None, no_migrate=False):
        self.stdout.write(f'正在安装插件: {plugin_name}')

        app_label = None

        if plugin_name.endswith('.zip'):
            if not os.path.exists(plugin_name):
                raise CommandError(f'zip 文件不存在: {plugin_name}')
            app_label = self.install_from_zip(plugin_name, force=force, no_migrate=no_migrate)
        elif os.path.exists(plugin_name) and os.path.isdir(plugin_name):
            app_label = self.install_from_path(plugin_name)
        else:
            plugin_path = os.path.join(
                settings.BASE_DIR, 'plugins', plugin_name
            )
            if os.path.exists(plugin_path) and os.path.isdir(plugin_path):
                app_label = self.install_from_path(plugin_path)
            elif plugin_name in ALL_AVAILABLE_PLUGINS:
                plugin_info = ALL_AVAILABLE_PLUGINS[plugin_name]
                app_label = self.install_builtin_plugin(
                    plugin_id=plugin_name, plugin_info=plugin_info
                )
            else:
                found = False
                for pid, pinfo in ALL_AVAILABLE_PLUGINS.items():
                    if pinfo['name'].lower() == plugin_name.lower():
                        app_label = self.install_builtin_plugin(
                            plugin_id=pid, plugin_info=pinfo
                        )
                        found = True
                        break
                if not found:
                    if source and source.endswith('.zip') and os.path.exists(source):
                        app_label = self.install_from_zip(source, force=force, no_migrate=no_migrate)
                    elif source and os.path.exists(source) and os.path.isdir(source):
                        app_label = self.install_from_path(source)
                    else:
                        app_label = self.install_from_registry(
                            plugin_name, registry_url, force
                        )

        if app_label and not no_migrate:
            self._run_migrate(app_label)

    def install_from_zip(self, zip_path, force=False, no_migrate=False):
        if not zipfile.is_zipfile(zip_path):
            raise CommandError(f'不是有效的 zip 文件: {zip_path}')

        plugins_base = os.path.join(settings.BASE_DIR, 'plugins')
        zip_basename = os.path.basename(zip_path)
        plugin_dir_name = os.path.splitext(zip_basename)[0]

        with zipfile.ZipFile(zip_path, 'r') as zf:
            top_dirs = set()
            for name in zf.namelist():
                parts = name.split('/')
                if len(parts) > 1 and parts[0]:
                    top_dirs.add(parts[0])

            if len(top_dirs) == 1:
                single_dir = top_dirs.pop()
                if single_dir == plugin_dir_name or single_dir.replace('-', '_') == plugin_dir_name:
                    plugin_dir_name = single_dir

            if len(top_dirs) == 1:
                single_dir = list(top_dirs)[0] if not plugin_dir_name else plugin_dir_name
                has_init = any(
                    n == f'{single_dir}/__init__.py' or n.startswith(f'{single_dir}/')
                    for n in zf.namelist()
                    if n.endswith('__init__.py')
                )
                if not has_init:
                    nested = [n for n in zf.namelist()
                              if n.startswith(f'{single_dir}/') and n.endswith('/')]
                    if nested:
                        for sub in nested:
                            sub_name = sub.rstrip('/').split('/')[-1]
                            sub_init = f'{single_dir}/{sub_name}/__init__.py'
                            if sub_init in zf.namelist():
                                plugin_dir_name = sub_name
                                break

        target_dir = os.path.join(plugins_base, plugin_dir_name)
        if os.path.exists(target_dir):
            if force:
                shutil.rmtree(target_dir)
            else:
                raise CommandError(
                    f'插件目录已存在: {target_dir}\n'
                    f'使用 --force 强制重新安装'
                )

        self.stdout.write(f'正在从 zip 文件解压插件: {zip_path}')

        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp_dir)

            extracted_items = os.listdir(tmp_dir)
            if len(extracted_items) == 1 and os.path.isdir(
                os.path.join(tmp_dir, extracted_items[0])
            ):
                src_dir = os.path.join(tmp_dir, extracted_items[0])
                inner_items = os.listdir(src_dir)
                has_init = '__init__.py' in inner_items
                if has_init:
                    plugin_dir_name = extracted_items[0]
                    target_dir = os.path.join(plugins_base, plugin_dir_name)
                    if os.path.exists(target_dir):
                        if force:
                            shutil.rmtree(target_dir)
                        else:
                            raise CommandError(
                                f'插件目录已存在: {target_dir}\n'
                                f'使用 --force 强制重新安装'
                            )
                    shutil.copytree(src_dir, target_dir)
                else:
                    sub_dirs = [
                        d for d in inner_items
                        if os.path.isdir(os.path.join(src_dir, d))
                        and os.path.exists(os.path.join(src_dir, d, '__init__.py'))
                    ]
                    if len(sub_dirs) == 1:
                        plugin_dir_name = sub_dirs[0]
                        target_dir = os.path.join(plugins_base, plugin_dir_name)
                        if os.path.exists(target_dir):
                            if force:
                                shutil.rmtree(target_dir)
                            else:
                                raise CommandError(
                                    f'插件目录已存在: {target_dir}\n'
                                    f'使用 --force 强制重新安装'
                                )
                        shutil.copytree(
                            os.path.join(src_dir, sub_dirs[0]), target_dir
                        )
                    else:
                        shutil.copytree(src_dir, target_dir)
            else:
                shutil.copytree(tmp_dir, target_dir)

        self.stdout.write(self.style.SUCCESS(
            f'插件已解压到: {target_dir}'
        ))

        app_label = self.install_from_path(target_dir)
        return app_label

    def install_from_registry(self, plugin_name, registry_url=None, force=False):
        remote_plugins = self._fetch_registry(registry_url)

        plugin_info = None
        for pid, info in remote_plugins.items():
            if pid == plugin_name or info.get('name', '').lower() == plugin_name.lower():
                plugin_info = info
                plugin_name = pid
                break

        if not plugin_info:
            available = list(remote_plugins.keys())
            raise CommandError(
                f'在远程仓库中找不到插件: {plugin_name}\n'
                f'可用的远程插件: {available}'
            )

        repository_url = plugin_info.get('repository')
        if not repository_url:
            raise CommandError(f'插件 {plugin_name} 没有提供仓库地址')

        target_dir = os.path.join(settings.BASE_DIR, 'plugins', plugin_name)
        if os.path.exists(target_dir):
            if force:
                shutil.rmtree(target_dir)
            else:
                raise CommandError(
                    f'插件目录已存在: {target_dir}\n'
                    f'使用 --force 强制重新安装'
                )

        self.stdout.write(f'正在从 {repository_url} 克隆插件...')

        clone_url = repository_url
        if repository_url.startswith('https://github.com/'):
            clone_url = repository_url.replace('https://github.com/', 'git@github.com:')

        try:
            result = subprocess.run(
                ['git', 'clone', '--depth', '1', clone_url, target_dir],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode != 0:
                self.stdout.write('SSH 克隆失败，尝试 HTTPS...')
                result = subprocess.run(
                    ['git', 'clone', '--depth', '1', repository_url, target_dir],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode != 0:
                    raise CommandError(f'克隆插件仓库失败: {result.stderr.strip()}')
        except subprocess.TimeoutExpired:
            raise CommandError('克隆插件仓库超时')
        except FileNotFoundError:
            raise CommandError('未找到 git，请先安装 git')

        self.stdout.write(self.style.SUCCESS(f'插件仓库已克隆到: {target_dir}'))

        git_dir = os.path.join(target_dir, '.git')
        if os.path.exists(git_dir):
            shutil.rmtree(git_dir)
            self.stdout.write('已移除 .git 目录')

        plugin_record, created = PluginRecord.objects.update_or_create(
            plugin_id=plugin_name,
            defaults={
                'name': plugin_info.get('name', plugin_name),
                'version': plugin_info.get('version', '0.0.0'),
                'description': plugin_info.get('description', ''),
                'is_active': True,
            }
        )
        if created:
            self.stdout.write('已创建插件数据库记录')
        else:
            self.stdout.write('已更新插件数据库记录')

        self._try_register_cloned_plugin(plugin_name, target_dir, plugin_info)

        app_label = plugin_name
        self.stdout.write(self.style.SUCCESS(
            f'插件 {plugin_info.get("name", plugin_name)} 安装完成!'
        ))
        return app_label

    def _try_register_cloned_plugin(self, plugin_id, plugin_path, registry_info):
        plugin_class = None
        plugin_module_name = None

        plugin_class, plugin_module_name = self._load_plugin_class_from_package(
            plugin_id, plugin_path
        )

        if plugin_class:
            try:
                plugin_instance = plugin_class()
                plugin_manager = get_plugin_manager()
                plugin_manager.plugins[plugin_instance.plugin_id] = plugin_instance

                try:
                    plugin_instance.initialize()
                except Exception:
                    pass

                plugin_record, _ = PluginRecord.objects.update_or_create(
                    plugin_id=plugin_instance.plugin_id,
                    defaults={
                        'name': plugin_instance.name,
                        'version': plugin_instance.version,
                        'description': plugin_instance.description,
                        'is_active': True,
                    }
                )

                self.add_plugin_to_toml_config(plugin_instance.plugin_id, {
                    'name': plugin_instance.name,
                    'module': plugin_module_name,
                    'class': plugin_class.__name__,
                    'description': plugin_instance.description,
                    'version': plugin_instance.version,
                    'enabled': True
                })
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'插件类注册失败（插件文件已下载）: {str(e)}'
                ))
        else:
            self.stdout.write(self.style.WARNING(
                '未找到 PluginInterface 子类，插件已下载但未自动注册到 TOML 配置'
            ))
            self.stdout.write('你可能需要手动在 plugins.toml 中添加插件配置')

    def _load_plugin_class_from_package(self, plugin_id, plugin_path):
        plugin_class = None
        plugin_module_name = None
        mod_name = f'plugins.{plugin_id}'

        init_file = os.path.join(plugin_path, '__init__.py')
        if os.path.exists(init_file):
            try:
                init_module = importlib.import_module(mod_name)
                if hasattr(init_module, 'PLUGIN_INFO'):
                    pinfo = getattr(init_module, 'PLUGIN_INFO')
                    if 'main_class' in pinfo and hasattr(init_module, pinfo['main_class']):
                        plugin_class = getattr(init_module, pinfo['main_class'])
                        plugin_module_name = mod_name
                        if self.debug:
                            self.stdout.write(f'[DEBUG] 从 PLUGIN_INFO 找到插件类: {plugin_class.__name__}')

                if not plugin_class:
                    for attr_name in dir(init_module):
                        attr = getattr(init_module, attr_name)
                        if (inspect.isclass(attr) and
                            hasattr(attr, '__mro__') and
                            attr.__name__ != 'PluginInterface' and
                            any(hasattr(b, '__name__') and b.__name__ == 'PluginInterface'
                                for b in attr.__mro__)):
                            plugin_class = attr
                            plugin_module_name = mod_name
                            break
            except ImportError as e:
                if self.debug:
                    self.stdout.write(f'[DEBUG] import_module({mod_name}) 失败: {e}')

                try:
                    spec = importlib.util.spec_from_file_location(
                        mod_name, init_file
                    )
                    if spec is not None and spec.loader is not None:
                        init_module = importlib.util.module_from_spec(spec)
                        sys.modules[mod_name] = init_module
                        spec.loader.exec_module(init_module)

                        if hasattr(init_module, 'PLUGIN_INFO'):
                            pinfo = getattr(init_module, 'PLUGIN_INFO')
                            if 'main_class' in pinfo and hasattr(init_module, pinfo['main_class']):
                                plugin_class = getattr(init_module, pinfo['main_class'])
                                plugin_module_name = mod_name

                        if not plugin_class:
                            for attr_name in dir(init_module):
                                attr = getattr(init_module, attr_name)
                                if (inspect.isclass(attr) and
                                    hasattr(attr, '__mro__') and
                                    attr.__name__ != 'PluginInterface' and
                                    any(hasattr(b, '__name__') and b.__name__ == 'PluginInterface'
                                        for b in attr.__mro__)):
                                    plugin_class = attr
                                    plugin_module_name = mod_name
                                    break
                except Exception as e2:
                    if self.debug:
                        self.stdout.write(f'[DEBUG] spec_from_file_location 也失败: {e2}')

        if not plugin_class:
            plugin_class, plugin_module_name = self._scan_py_files_for_plugin(
                plugin_id, plugin_path
            )

        if self.debug:
            if plugin_class:
                self.stdout.write(f'[DEBUG] 找到插件类: {plugin_class.__name__} from {plugin_module_name}')
            else:
                self.stdout.write(f'[DEBUG] 未找到插件类 in {plugin_path}')

        return plugin_class, plugin_module_name

    def _scan_py_files_for_plugin(self, plugin_id, plugin_path):
        py_files = [
            f for f in os.listdir(plugin_path)
            if f.endswith('.py') and f != '__init__.py'
        ]
        for pf in py_files:
            fp = os.path.join(plugin_path, pf)
            try:
                with open(fp, 'r', encoding='utf-8') as f:
                    content = f.read()
                if not re.search(
                    r'class\s+\w+\s*\([^)]*PluginInterface',
                    content, re.DOTALL
                ):
                    continue

                mod_name = f'plugins.{plugin_id}.{pf[:-3]}'
                try:
                    module = importlib.import_module(mod_name)
                except ImportError:
                    spec = importlib.util.spec_from_file_location(
                        f"external_plugin_{plugin_id}", fp
                    )
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = module
                    spec.loader.exec_module(module)

                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if not inspect.isclass(attr) or not hasattr(attr, '__mro__'):
                        continue
                    if attr.__name__ == 'PluginInterface':
                        continue
                    if any(
                        hasattr(base, '__name__') and base.__name__ == 'PluginInterface'
                        for base in attr.__mro__
                    ):
                        return attr, mod_name
            except Exception:
                continue

        return None, None

    def install_from_path(self, plugin_path):
        if not os.path.exists(plugin_path):
            raise CommandError(f'插件路径不存在: {plugin_path}')

        plugin_dir_name = os.path.basename(os.path.abspath(plugin_path))
        plugins_base = os.path.join(settings.BASE_DIR, 'plugins')
        is_under_plugins = (
            os.path.dirname(os.path.abspath(plugin_path)) ==
            os.path.abspath(plugins_base)
        )

        plugin_manager = get_plugin_manager()
        loaded_plugins = plugin_manager.get_all_plugins()

        plugin_class = None
        plugin_module_name = None

        if is_under_plugins:
            plugin_class, plugin_module_name = (
                self._load_plugin_class_from_package(
                    plugin_dir_name, plugin_path
                )
            )
        else:
            plugin_class, plugin_module_name = (
                self._load_plugin_class_from_external(plugin_path)
            )

        if not plugin_class:
            raise CommandError(
                f'在 {plugin_path} 中未找到有效的插件类\n'
                f'请确保插件目录中包含继承自 PluginInterface 的类'
            )

        try:
            plugin_instance = plugin_class()

            if plugin_instance.plugin_id in loaded_plugins:
                self.stdout.write(self.style.WARNING(
                    f'插件 {plugin_instance.name} (ID: {plugin_instance.plugin_id}) 已加载，跳过重复安装'
                ))
                return self._get_app_label_from_module(plugin_module_name)

            plugin_manager.plugins[plugin_instance.plugin_id] = (
                plugin_instance
            )

            from plugins.core.base import ServiceProvider
            if isinstance(plugin_instance, ServiceProvider):
                plugin_manager.service_registry.register(plugin_instance)

            try:
                if plugin_instance.initialize():
                    self.stdout.write(self.style.SUCCESS(
                        f'成功从路径安装插件: {plugin_instance.name}'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'插件 {plugin_instance.name} 安装成功但初始化失败'
                    ))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'插件 {plugin_instance.name} 初始化出错: {str(e)}'
                ))

            plugin_record, created = PluginRecord.objects.update_or_create(
                plugin_id=plugin_instance.plugin_id,
                defaults={
                    'name': plugin_instance.name,
                    'version': plugin_instance.version,
                    'description': plugin_instance.description,
                    'is_active': True,
                }
            )

            if created:
                self.stdout.write('已创建插件数据库记录')
            else:
                self.stdout.write('已更新插件数据库记录')

            self.add_plugin_to_toml_config(plugin_instance.plugin_id, {
                'name': plugin_instance.name,
                'module': plugin_module_name,
                'class': plugin_class.__name__,
                'description': plugin_instance.description,
                'version': plugin_instance.version,
                'enabled': True
            })

            self.stdout.write(self.style.SUCCESS(
                f'插件 {plugin_instance.name} (v{plugin_instance.version}) 安装完成！'
            ))
            self.stdout.write(
                '提示: 需要重启服务以使 Django App 注册生效'
            )

            return self._get_app_label_from_module(plugin_module_name)
        except CommandError:
            raise
        except Exception as e:
            raise CommandError(f'从路径安装插件失败: {str(e)}')

    def _load_plugin_class_from_external(self, plugin_path):
        plugin_class = None
        plugin_module_name = None
        plugin_dir_name = os.path.basename(plugin_path)

        init_file = os.path.join(plugin_path, '__init__.py')
        if os.path.exists(init_file):
            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugin_init_{plugin_dir_name}", init_file
                )
                if spec is not None and spec.loader is not None:
                    init_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(init_module)
                    if hasattr(init_module, 'PLUGIN_INFO'):
                        pinfo = getattr(init_module, 'PLUGIN_INFO')
                        mc = pinfo.get('main_class')
                        if mc and hasattr(init_module, mc):
                            plugin_class = getattr(init_module, mc)
                            plugin_module_name = (
                                f'plugins.{plugin_dir_name}'
                            )
            except Exception:
                pass

        if not plugin_class:
            py_files = [
                f for f in os.listdir(plugin_path)
                if f.endswith('.py') and f != '__init__.py'
            ]
            for pf in py_files:
                fp = os.path.join(plugin_path, pf)
                try:
                    with open(fp, 'r', encoding='utf-8') as f:
                        content = f.read()
                    if not re.search(
                        r'class\s+\w+\s*\([^)]*PluginInterface',
                        content, re.DOTALL
                    ):
                        continue

                    mod_name = f'plugins.{plugin_dir_name}.{pf[:-3]}'
                    spec = importlib.util.spec_from_file_location(
                        mod_name, fp
                    )
                    if spec is None or spec.loader is None:
                        continue
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[mod_name] = module
                    spec.loader.exec_module(module)

                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if not inspect.isclass(attr):
                            continue
                        if attr.__name__ == 'PluginInterface':
                            continue
                        if not hasattr(attr, '__mro__'):
                            continue
                        if any(
                            hasattr(b, '__name__') and
                            b.__name__ == 'PluginInterface'
                            for b in attr.__mro__
                        ):
                            return attr, mod_name
                except Exception:
                    continue

        return plugin_class, plugin_module_name

    def install_builtin_plugin(self, plugin_id, plugin_info):
        plugin_manager = get_plugin_manager()

        if plugin_id in plugin_manager.get_all_plugins():
            self.stdout.write(
                self.style.WARNING(f'插件 {plugin_info["name"]} 已经加载.')
            )
            return self._get_app_label_from_module(
                plugin_info.get('module', '')
            )

        plugin = plugin_manager.load_builtin_plugin(plugin_id, plugin_info)
        if not plugin:
            raise CommandError(f'加载插件 {plugin_info["name"]} 失败')

        try:
            if plugin.initialize():
                self.stdout.write(self.style.SUCCESS(
                    f'成功安装并初始化插件: {plugin.name}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'插件 {plugin.name} 安装成功但初始化失败'
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'插件 {plugin.name} 安装成功但初始化出错: {str(e)}'
            ))

        plugin_record, created = PluginRecord.objects.update_or_create(
            plugin_id=plugin.plugin_id,
            defaults={
                'name': plugin.name,
                'version': plugin.version,
                'description': plugin.description,
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(f'已创建插件数据库记录')

        if plugin_id not in ALL_AVAILABLE_PLUGINS:
            self.add_plugin_to_toml_config(plugin_id, plugin_info)

        return self._get_app_label_from_module(
            plugin_info.get('module', '')
        )

    def uninstall_plugin(self, plugin_name, force=False, no_migrate=False):
        self.stdout.write(f'正在卸载插件: {plugin_name}')

        plugin_manager = get_plugin_manager()

        plugin = None
        loaded_plugins = plugin_manager.get_all_plugins()
        app_label = None
        for pid, p in loaded_plugins.items():
            if p.plugin_id == plugin_name or p.name.lower() == plugin_name.lower():
                plugin = p
                app_label = pid
                break

        if not plugin:
            db_record = PluginRecord.objects.filter(plugin_id=plugin_name).first()
            if db_record:
                if force or input(f'插件 {plugin_name} 未加载但数据库中有记录。是否删除数据库记录？(y/N): ').lower() == 'y':
                    if not no_migrate:
                        self._run_migrate_reverse(plugin_name)
                    PluginRecord.objects.filter(plugin_id=plugin_name).delete()
                    self.remove_plugin_from_toml_config(plugin_name)
                    plugin_dir = os.path.join(settings.BASE_DIR, 'plugins', plugin_name)
                    if os.path.exists(plugin_dir):
                        shutil.rmtree(plugin_dir)
                        self.stdout.write(f'已删除插件目录: {plugin_dir}')
                    self.stdout.write(self.style.SUCCESS(f'已从数据库中删除插件记录: {plugin_name}'))
                    return
                else:
                    self.stdout.write(f'操作已取消')
                    return
            else:
                raise CommandError(f'找不到已加载的插件: {plugin_name}')

        try:
            if hasattr(plugin, 'shutdown'):
                plugin.shutdown()

            success = plugin_manager.unload_plugin(plugin.plugin_id)

            if success:
                if not no_migrate and app_label:
                    self._run_migrate_reverse(app_label)
                PluginRecord.objects.filter(plugin_id=plugin.plugin_id).update(is_active=False)
                self.remove_plugin_from_toml_config(plugin.plugin_id)
                plugin_dir = os.path.join(settings.BASE_DIR, 'plugins', plugin.plugin_id)
                if os.path.exists(plugin_dir):
                    shutil.rmtree(plugin_dir)
                    self.stdout.write(f'已删除插件目录: {plugin_dir}')
                self.stdout.write(self.style.SUCCESS(f'成功卸载插件: {plugin.name}'))
            else:
                raise CommandError(f'卸载插件 {plugin.name} 失败')
        except Exception as e:
            if force:
                if not no_migrate and app_label:
                    self._run_migrate_reverse(app_label)
                PluginRecord.objects.filter(plugin_id=plugin.plugin_id).delete()
                self.remove_plugin_from_toml_config(plugin.plugin_id)
                plugin_dir = os.path.join(settings.BASE_DIR, 'plugins', plugin.plugin_id)
                if os.path.exists(plugin_dir):
                    shutil.rmtree(plugin_dir)
                self.stdout.write(self.style.WARNING(f'强制卸载插件: {plugin.name}'))
            else:
                raise CommandError(f'卸载插件失败: {str(e)}')

    def list_plugins(self):
        self.stdout.write(self.style.SUCCESS('已安装的插件:'))

        plugin_manager = get_plugin_manager()
        loaded_plugins = plugin_manager.get_all_plugins()

        if not loaded_plugins:
            self.stdout.write('  没有加载任何插件')
        else:
            for plugin_id, plugin in loaded_plugins.items():
                status = '✓' if hasattr(plugin, 'enabled') and plugin.enabled else '✓'
                self.stdout.write(f'  [{status}] {plugin.name} (v{plugin.version}) - {plugin.description}')

        db_records = PluginRecord.objects.all()
        if db_records.exists():
            self.stdout.write('\n数据库中的插件记录:')
            for record in db_records:
                status = '✓' if record.is_active else '✗'
                is_available = record.plugin_id in ALL_AVAILABLE_PLUGINS
                availability_indicator = '●' if is_available else '○'
                self.stdout.write(f'  [{status}{availability_indicator}] {record.name} (v{record.version}) - {record.plugin_id}')

        self.stdout.write('\n可用插件:')
        installed_plugin_ids = {p.plugin_id for p in loaded_plugins.values()}
        for plugin_id, plugin_info in ALL_AVAILABLE_PLUGINS.items():
            status = '✓' if plugin_id in installed_plugin_ids else '○'
            self.stdout.write(f'  [{status}] {plugin_info["name"]} - {plugin_info["description"]}')

        self.stdout.write('\n远程仓库插件 (使用 plugins search 查看更多):')
        try:
            remote_plugins = self._fetch_registry()
            for plugin_id, info in remote_plugins.items():
                installed = '✓' if plugin_id in installed_plugin_ids else '○'
                self.stdout.write(f'  [{installed}] {info.get("name", plugin_id)} - {info.get("description", "N/A")}')
        except Exception:
            self.stdout.write(self.style.WARNING('  无法连接远程仓库'))

    def plugin_info(self, plugin_name):
        plugin_manager = get_plugin_manager()

        loaded_plugins = plugin_manager.get_all_plugins()
        plugin = None
        for pid, p in loaded_plugins.items():
            if p.plugin_id == plugin_name or p.name.lower() == plugin_name.lower():
                plugin = p
                break

        if not plugin:
            for plugin_id, plugin_info in ALL_AVAILABLE_PLUGINS.items():
                if plugin_id == plugin_name or plugin_info['name'].lower() == plugin_name.lower():
                    self.stdout.write(f'插件信息: {plugin_info["name"]}')
                    self.stdout.write(f'  ID: {plugin_id}')
                    self.stdout.write(f'  版本: {plugin_info["version"]}')
                    self.stdout.write(f'  描述: {plugin_info["description"]}')
                    self.stdout.write(f'  模块: {plugin_info["module"]}')
                    self.stdout.write(f'  类: {plugin_info["class"]}')
                    self.stdout.write(f'  状态: {"已启用" if plugin_info["enabled"] else "已禁用"}')
                    return

        if plugin:
            self.stdout.write(f'插件信息: {plugin.name}')
            self.stdout.write(f'  ID: {plugin.plugin_id}')
            self.stdout.write(f'  版本: {plugin.version}')
            self.stdout.write(f'  描述: {plugin.description}')
            if hasattr(plugin, 'enabled'):
                self.stdout.write(f'  状态: {"已启用" if plugin.enabled else "已禁用"}')
            else:
                self.stdout.write(f'  状态: 已加载')
        else:
            try:
                remote_plugins = self._fetch_registry()
                for plugin_id, info in remote_plugins.items():
                    if plugin_id == plugin_name or info.get('name', '').lower() == plugin_name.lower():
                        self.stdout.write(f'远程插件信息: {info.get("name", plugin_id)}')
                        self.stdout.write(f'  ID: {plugin_id}')
                        self.stdout.write(f'  版本: {info.get("version", "N/A")}')
                        self.stdout.write(f'  描述: {info.get("description", "N/A")}')
                        self.stdout.write(f'  仓库: {info.get("repository", "N/A")}')
                        return
            except Exception:
                pass

            db_record = PluginRecord.objects.filter(plugin_id=plugin_name).first()
            if db_record:
                self.stdout.write(f'插件信息: {db_record.name}')
                self.stdout.write(f'  ID: {db_record.plugin_id}')
                self.stdout.write(f'  版本: {db_record.version}')
                self.stdout.write(f'  描述: {db_record.description}')
                self.stdout.write(f'  状态: {"已激活" if db_record.is_active else "未激活"}')
                self.stdout.write(f'  注意: 此插件在数据库中有记录，但当前版本中不可用（可能是私有插件）')
            else:
                raise CommandError(f'找不到插件: {plugin_name}')

    def add_plugin_to_toml_config(self, plugin_id, plugin_info):
        config_file_path = os.path.join(settings.BASE_DIR, 'plugins', 'plugins.toml')

        if os.path.exists(config_file_path):
            with open(config_file_path, 'r', encoding='utf-8') as f:
                toml_data = toml.load(f)
        else:
            toml_data = {
                'builtin': {},
                'third_party': {}
            }

        if plugin_id in toml_data.get('builtin', {}) or plugin_id in toml_data.get('third_party', {}):
            self.stdout.write(f'插件 {plugin_id} 已存在于配置中')
            return

        toml_data.setdefault('third_party', {})[plugin_id] = {
            'name': plugin_info['name'],
            'module': plugin_info['module'],
            'class': plugin_info['class'],
            'description': plugin_info['description'],
            'version': plugin_info['version'],
            'enabled': plugin_info['enabled']
        }

        with open(config_file_path, 'w', encoding='utf-8') as f:
            toml.dump(toml_data, f)

        self.stdout.write(f'已将插件 {plugin_id} 添加到 TOML 配置文件')

    def remove_plugin_from_toml_config(self, plugin_id):
        config_file_path = os.path.join(settings.BASE_DIR, 'plugins', 'plugins.toml')

        if not os.path.exists(config_file_path):
            self.stdout.write(f'TOML 配置文件不存在: {config_file_path}')
            return

        with open(config_file_path, 'r', encoding='utf-8') as f:
            toml_data = toml.load(f)

        plugin_removed = False
        if 'builtin' in toml_data and plugin_id in toml_data['builtin']:
            del toml_data['builtin'][plugin_id]
            plugin_removed = True
            self.stdout.write(f'已从 builtin 部分移除插件 {plugin_id}')

        if 'third_party' in toml_data and plugin_id in toml_data['third_party']:
            del toml_data['third_party'][plugin_id]
            plugin_removed = True
            self.stdout.write(f'已从 third_party 部分移除插件 {plugin_id}')

        if plugin_removed:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                toml.dump(toml_data, f)

            self.stdout.write(f'已从 TOML 配置文件中移除插件 {plugin_id}')
        else:
            self.stdout.write(f'插件 {plugin_id} 在 TOML 配置文件中未找到')

    def _resolve_plugin_id(self, plugin_name):
        plugin_manager = get_plugin_manager()
        loaded_plugins = plugin_manager.get_all_plugins()

        for pid, p in loaded_plugins.items():
            if p.plugin_id == plugin_name or p.name.lower() == plugin_name.lower():
                return p.plugin_id

        for plugin_id, plugin_info in ALL_AVAILABLE_PLUGINS.items():
            if plugin_id == plugin_name or plugin_info.get('name', '').lower() == plugin_name.lower():
                return plugin_id

        db_record = PluginRecord.objects.filter(plugin_id=plugin_name).first()
        if not db_record:
            db_record = PluginRecord.objects.filter(
                name__iexact=plugin_name
            ).first()
        if db_record:
            return db_record.plugin_id

        return None

    def enable_plugin(self, plugin_name):
        plugin_id = self._resolve_plugin_id(plugin_name)
        if not plugin_id:
            raise CommandError(f'找不到插件: {plugin_name}')

        plugin_manager = get_plugin_manager()
        loaded_plugins = plugin_manager.get_all_plugins()

        if plugin_id in loaded_plugins:
            self.stdout.write(self.style.WARNING(
                f'插件 {plugin_id} 已加载且处于启用状态'
            ))
            self.update_plugin_enabled_in_toml(plugin_id, True)
            PluginRecord.objects.filter(plugin_id=plugin_id).update(
                is_active=True
            )
            return

        plugin_info = ALL_AVAILABLE_PLUGINS.get(plugin_id)
        if plugin_info:
            plugin = plugin_manager.load_builtin_plugin(plugin_id, plugin_info)
            if plugin:
                try:
                    plugin.initialize()
                    self.stdout.write(self.style.SUCCESS(
                        f'成功启用并初始化插件: {plugin.name}'
                    ))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'插件 {plugin.name} 启用成功但初始化失败: {str(e)}'
                    ))
            else:
                raise CommandError(f'加载插件 {plugin_id} 失败')
        else:
            self.stdout.write(self.style.WARNING(
                f'插件 {plugin_id} 不在可用插件列表中，仅更新配置和数据库状态'
            ))

        self.update_plugin_enabled_in_toml(plugin_id, True)
        PluginRecord.objects.update_or_create(
            plugin_id=plugin_id,
            defaults={'is_active': True}
        )
        self.stdout.write(self.style.SUCCESS(f'插件 {plugin_id} 已启用'))

    def disable_plugin(self, plugin_name):
        plugin_id = self._resolve_plugin_id(plugin_name)
        if not plugin_id:
            raise CommandError(f'找不到插件: {plugin_name}')

        plugin_manager = get_plugin_manager()
        loaded_plugins = plugin_manager.get_all_plugins()

        if plugin_id in loaded_plugins:
            plugin = loaded_plugins[plugin_id]
            try:
                if hasattr(plugin, 'shutdown'):
                    plugin.shutdown()
                plugin_manager.unload_plugin(plugin_id)
                self.stdout.write(f'已卸载插件: {plugin.name}')
            except Exception as e:
                raise CommandError(f'卸载插件 {plugin.name} 失败: {str(e)}')

        self.update_plugin_enabled_in_toml(plugin_id, False)
        PluginRecord.objects.filter(plugin_id=plugin_id).update(
            is_active=False
        )
        self.stdout.write(self.style.SUCCESS(f'插件 {plugin_id} 已禁用'))

    def update_plugin_enabled_in_toml(self, plugin_id, enabled):
        config_file_path = os.path.join(
            settings.BASE_DIR, 'plugins', 'plugins.toml'
        )

        if not os.path.exists(config_file_path):
            self.stdout.write(self.style.WARNING(
                f'TOML 配置文件不存在: {config_file_path}'
            ))
            return False

        with open(config_file_path, 'r', encoding='utf-8') as f:
            toml_data = toml.load(f)

        updated = False
        for section in ('builtin', 'third_party'):
            if section in toml_data and plugin_id in toml_data[section]:
                toml_data[section][plugin_id]['enabled'] = enabled
                updated = True
                break

        if not updated:
            self.stdout.write(self.style.WARNING(
                f'插件 {plugin_id} 在 TOML 配置文件中未找到，将添加配置'
            ))
            toml_data.setdefault('third_party', {})[plugin_id] = {
                'enabled': enabled
            }
            updated = True

        if updated:
            with open(config_file_path, 'w', encoding='utf-8') as f:
                toml.dump(toml_data, f)
            state = '启用' if enabled else '禁用'
            self.stdout.write(
                f'已更新 TOML 配置: 插件 {plugin_id} -> {state}'
            )

        return updated

    def _get_app_label_from_module(self, module_name):
        if not module_name:
            return None
        parts = module_name.rsplit('.', 1)
        if len(parts) == 2 and parts[0].startswith('plugins.'):
            return parts[0].split('.')[1]
        return None

    def _run_migrate(self, app_label):
        import subprocess
        import sys
        self.stdout.write(f'正在执行数据库迁移: {app_label}')
        if self.debug:
            from django.apps import apps
            installed = [a.label for a in apps.get_app_configs()]
            self.stdout.write(f'[DEBUG] 已注册 App labels: {installed}')
            self.stdout.write(f'[DEBUG] {app_label} is_installed: {apps.is_installed(app_label)}')
        try:
            result = subprocess.run(
                [sys.executable, 'manage.py', 'migrate', app_label, '--verbosity=2' if self.debug else '--verbosity=0'],
                capture_output=True, text=True,
                cwd=str(settings.BASE_DIR),
            )
            if self.debug and result.stdout:
                self.stdout.write(f'[DEBUG] migrate stdout:\n{result.stdout}')
            if self.debug and result.stderr:
                self.stdout.write(f'[DEBUG] migrate stderr:\n{result.stderr}')
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(
                    f'数据库迁移完成: {app_label}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'数据库迁移失败: {result.stderr.strip()}'
                ))
                self.stdout.write(
                    '你可以手动执行: '
                    f'python manage.py migrate {app_label}'
                )
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'数据库迁移失败: {str(e)}'
            ))

    def _run_migrate_reverse(self, app_label):
        import subprocess
        import sys
        self.stdout.write(f'正在回滚数据库迁移: {app_label}')
        try:
            result = subprocess.run(
                [
                    sys.executable, 'manage.py',
                    'migrate', app_label, 'zero',
                ],
                capture_output=True, text=True,
                cwd=str(settings.BASE_DIR),
            )
            if result.returncode == 0:
                self.stdout.write(self.style.SUCCESS(
                    f'数据库迁移已回滚: {app_label}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'数据库迁移回滚失败: {result.stderr.strip()}'
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'数据库迁移回滚失败: {str(e)}'
            ))

    def upgrade_plugin(self, plugin_name, registry_url=None):
        self.stdout.write(f'正在升级插件: {plugin_name}')

        plugin_info = ALL_AVAILABLE_PLUGINS.get(plugin_name)
        if not plugin_info:
            for pid, pinfo in ALL_AVAILABLE_PLUGINS.items():
                if pinfo['name'].lower() == plugin_name.lower():
                    plugin_info = pinfo
                    plugin_name = pid
                    break

        if not plugin_info:
            self.stdout.write(
                '插件未在本地配置中找到，尝试从远程仓库更新...'
            )
            self.install_from_registry(
                plugin_name, registry_url, force=True
            )
            return

        app_label = self._get_app_label_from_module(
            plugin_info.get('module', '')
        )
        if app_label:
            self._run_migrate(app_label)

        self.stdout.write(self.style.SUCCESS(
            f'插件 {plugin_name} 升级完成'
        ))
