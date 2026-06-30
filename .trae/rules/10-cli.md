# 10 - CLI 工具

## 入口

```bash
2c2a --help                     # 查看所有命令
2c2a <command> --help           # 子命令帮助
python -m app.cli               # 备用入口
```

## 命令结构

```
2c2a
├── collectstatic [dest] [--clear] [--dry-run]   # 静态资源收集
├── keys (generate/secret/aes/blake2b/ed25519/show)  # 密钥生成
├── db (init/migrate/upgrade/downgrade/history/current/heads/reset)  # 数据库
├── account (createsuperuser/create/list/changepassword/activate/...) # 账户
├── serve (serve/worker/shell/check)              # 服务器
├── plugin (list/info/enable/disable/reload/routes/services/scaffold) # 插件
├── tenant (list/create/info/add-hostname/remove-hostname/...)        # 租户
├── migrate                                       # 快捷
├── createsuperuser                               # 快捷
└── runserver                                     # 快捷
```

## 命令文件组织

```
app/cli/
├── main.py       # 主入口
├── utils.py      # 共享工具（run_async / db_session / 输出）
├── db.py         # 数据库
├── account.py    # 账户
├── server.py     # 服务器
├── plugins.py    # 插件
├── tenant.py     # 租户
├── static.py     # collectstatic + keys
└── __main__.py   # python -m 入口
```

## 异步命令

CLI 是同步入口，用 `run_async` 包装异步操作：

```python
from app.cli.utils import run_async, db_session

@account_app.command("create")
def create_user(username: str, ...):
    async def _do():
        async with db_session() as session:
            user = User(username=username, ...)
            session.add(user)
    run_async(_do())
```

## 输出

用 `app/cli/utils.py` 的辅助函数：

```python
from app.cli.utils import console, success, error, info, warn, print_table

success("用户创建成功")
error("用户不存在")
print_table("用户列表", ["ID", "用户名", "邮箱"], rows)
```

## 密码交互

```python
from app.cli.utils import blake2b_prehash_interactive
from app.security.password import hash_password

prehash = blake2b_prehash_interactive("密码")
phc = hash_password(prehash)
user.password_hash = phc
```

## 关系加载

CLI 中访问模型关系**必须**用 `selectinload` 预加载：

```python
from sqlalchemy.orm import selectinload

result = await session.execute(
    select(User).options(selectinload(User.active_ban)).where(User.username == username)
)
```