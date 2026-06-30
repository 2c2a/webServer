"""add site_group_id to ticket

Revision ID: c3d4e5f6a7b8
Revises: a1b2c3d4e5f6
Create Date: 2026-06-24 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 添加 site_group_id 列（nullable，历史数据为 NULL）
    op.add_column(
        "ticket",
        sa.Column("site_group_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_ticket_site_group_id",
        "ticket",
        "site_group",
        ["site_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 添加索引以加速租户过滤查询
    op.create_index(
        "ix_ticket_site_group_id",
        "ticket",
        ["site_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ticket_site_group_id", table_name="ticket")
    op.drop_constraint("fk_ticket_site_group_id", "ticket", type_="foreignkey")
    op.drop_column("ticket", "site_group_id")
