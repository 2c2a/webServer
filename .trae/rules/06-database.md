# 06 - 数据库模型

## 技术栈

SQLAlchemy 2.0 异步，`Mapped`/`mapped_column` 新语法。

## 基类与 Mixin

```python
from app.models.base import Base, TimestampMixin, SiteGroupMixin, UUIDPKMixin
```

| Mixin | 字段 | 用途 |
| --- | --- | --- |
| `Base` | - | 声明式基类 |
| `TimestampMixin` | `created_at`, `updated_at` | 时间戳（自动维护） |
| `SiteGroupMixin` | `site_group_id` | 租户隔离 |
| `UUIDPKMixin` | `id` (UUID) | 分布式场景 |

## 模型定义规范

```python
from sqlalchemy import String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, TimestampMixin

class Host(Base, TimestampMixin):
    __tablename__ = "hosts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    site_group_id: Mapped[int] = mapped_column(ForeignKey("site_groups.id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    site_group: Mapped["SiteGroup"] = relationship(back_populates="hosts")
```

### 规则

1. **必须**继承 `Base`
2. **必须**显式定义 `__tablename__`
3. 业务模型**必须**混入 `TimestampMixin`
4. 租户隔离模型**必须**加 `site_group_id` + ForeignKey + index
5. 用 `Mapped[type]` + `mapped_column()`，不用旧式 `Column`

## 关系预加载

```python
from sqlalchemy.orm import selectinload, joinedload

# selectinload：推荐，额外 IN 查询
result = await db.execute(
    select(User).options(selectinload(User.active_ban)).where(User.id == uid)
)

# joinedload：JOIN 一次性加载
result = await db.execute(
    select(Host).options(joinedload(Host.site_group))
)
```

**异步会话关闭后不能懒加载**，必须预加载。

## 新模型注册

新模型必须在 `app/models/__init__.py` 导入，否则 Alembic 无法发现。

## 禁止

1. 禁止用旧式 Column 语法
2. 禁止在模型中写业务逻辑（放 service 或路由）
3. 禁止跨租户查询