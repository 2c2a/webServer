"""添加站内信表 notification

Revision ID: e5f6a7b8c9d0
Revises: b444ba28185a
Create Date: 2026-06-30 22:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'b444ba28185a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notification',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=20), nullable=False),
        sa.Column('level', sa.String(length=20), nullable=False, server_default='info'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('body', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('ref_type', sa.String(length=50), nullable=True),
        sa.Column('ref_id', sa.Integer(), nullable=True),
        sa.Column('action_url', sa.String(length=500), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('site_group_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_group_id'], ['site_group.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    # 单列索引
    op.create_index(op.f('ix_notification_user_id'), 'notification', ['user_id'], unique=False)
    op.create_index(op.f('ix_notification_is_read'), 'notification', ['is_read'], unique=False)
    op.create_index(op.f('ix_notification_site_group_id'), 'notification', ['site_group_id'], unique=False)
    # 联合索引：用户未读数查询高频
    op.create_index('ix_notification_user_read', 'notification', ['user_id', 'is_read'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notification_user_read', table_name='notification')
    op.drop_index(op.f('ix_notification_site_group_id'), table_name='notification')
    op.drop_index(op.f('ix_notification_is_read'), table_name='notification')
    op.drop_index(op.f('ix_notification_user_id'), table_name='notification')
    op.drop_table('notification')
