# 07 - 数据库迁移

## 工具

Alembic（异步 env.py）。所有迁移操作通过 CLI 完成。

## 常用命令

```bash
2c2a db init                     # 初始化（create_all，开发用）
2c2a db migrate -m "描述"       # 生成迁移脚本
2c2a db upgrade                  # 升级到最新
2c2a db downgrade -1             # 回滚一个版本
2c2a db history                  # 查看历史
2c2a db current                  # 当前版本
2c2a db heads                    # 最新版本
2c2a db reset                    # 危险：重置数据库
```

快捷命令：`2c2a migrate -m "描述"`（生成 + 升级）

## 迁移工作流

```
1. 修改模型代码
2. 确保模型在 app/models/__init__.py 导入
3. 2c2a db migrate -m "描述变更"
4. 检查生成的迁移脚本（必须！autogenerate 不完美）
5. 2c2a db upgrade
6. 2c2a db current 验证
```

### 必须检查生成的迁移脚本

Alembic autogenerate 常见遗漏：
- server_default 变更
- 约束名变更
- 关系变更
- 枚举类型变更

## 迁移脚本规范

```python
def upgrade() -> None:
    op.add_column("hosts", sa.Column("new_field", sa.String(100), nullable=True))

def downgrade() -> None:
    op.drop_column("hosts", "new_field")
```

### 规则

1. **必须**实现 `downgrade()`，不能为空
2. **禁止** `SeparateDatabaseAndState` 空操作
3. 数据迁移用 `op.execute()` 或 `op.bulk_insert()`
4. 大表加列：先 nullable=True，回填数据，再改 NOT NULL

## 多租户表迁移

新增租户隔离表必须包含 `site_group_id` + 外键 + 索引：

```python
sa.Column("site_group_id", sa.Integer, sa.ForeignKey("site_groups.id"), nullable=False)
op.create_index("ix_new_table_site_group_id", "new_table", ["site_group_id"])
```

## 故障排查

```bash
# "Target database is not up to date"
2c2a db current
2c2a db heads
2c2a db upgrade

# "Multiple heads"
alembic merge -m "merge heads" head1 head2

# autogenerate 检测不到变更
# 确认模型在 app/models/__init__.py 导入
# 确认 Base.metadata 一致
```