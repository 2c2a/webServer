"""add site_group_id to audit_log

Revision ID: a1b2c3d4e5f6
Revises: 208e77e631c4
Create Date: 2026-06-23 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "208e77e631c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 site_group_id 列（nullable，历史数据为 NULL）
    op.add_column(
        "audit_log",
        sa.Column("site_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_log_site_group_id",
        "audit_log",
        "site_group",
        ["site_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 添加索引以加速租户过滤查询
    op.create_index(
        "ix_audit_log_site_group_id",
        "audit_log",
        ["site_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_site_group_id", table_name="audit_log")
    op.drop_constraint("fk_audit_log_site_group_id", "audit_log", type_="foreignkey")
    op.drop_column("audit_log", "site_group_id")
