"""add points system

积分系统：新增 point_task / point_record / user_points 三张表，
并为 product 表增加 required_points 列（默认 0）。

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-26 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 积分任务 ──
    op.create_table(
        "point_task",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("detection_method", sa.String(length=50), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("site_group_id", sa.Integer(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["site_group_id"], ["site_group.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_point_task_site_group_id", "point_task", ["site_group_id"], unique=False
    )

    # ── 积分明细流水 ──
    op.create_table(
        "point_record",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False),
        sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("ref_type", sa.String(length=50), nullable=True),
        sa.Column("ref_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("site_group_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["site_group_id"], ["site_group.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["point_task.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_point_record_user_id", "point_record", ["user_id"], unique=False
    )
    op.create_index(
        "ix_point_record_site_group_id",
        "point_record",
        ["site_group_id"],
        unique=False,
    )

    # ── 用户积分余额 ──
    op.create_table(
        "user_points",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("site_group_id", sa.Integer(), nullable=True),
        sa.Column("balance", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["site_group_id"], ["site_group.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "site_group_id", name="uq_user_sitegroup_points"
        ),
    )
    op.create_index(
        "ix_user_points_user_id", "user_points", ["user_id"], unique=False
    )
    op.create_index(
        "ix_user_points_site_group_id",
        "user_points",
        ["site_group_id"],
        unique=False,
    )

    # ── 产品积分门槛 ──
    op.add_column(
        "product",
        sa.Column(
            "required_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("product", "required_points")
    op.drop_index("ix_user_points_site_group_id", table_name="user_points")
    op.drop_index("ix_user_points_user_id", table_name="user_points")
    op.drop_table("user_points")
    op.drop_index("ix_point_record_site_group_id", table_name="point_record")
    op.drop_index("ix_point_record_user_id", table_name="point_record")
    op.drop_table("point_record")
    op.drop_index("ix_point_task_site_group_id", table_name="point_task")
    op.drop_table("point_task")
