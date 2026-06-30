"""add captcha scene config fields

Revision ID: 8a5078c06886
Revises: 0049ac7e24ac
Create Date: 2026-06-29 03:24:54.350173
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8a5078c06886'
down_revision: Union[str, None] = '0049ac7e24ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 新增 4 个布尔字段，server_default 确保已有行有值
    op.add_column('system_config', sa.Column('captcha_enabled', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('system_config', sa.Column('captcha_required_on_login', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('system_config', sa.Column('captcha_required_on_register', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('system_config', sa.Column('captcha_required_on_email', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column('system_config', 'captcha_required_on_email')
    op.drop_column('system_config', 'captcha_required_on_register')
    op.drop_column('system_config', 'captcha_required_on_login')
    op.drop_column('system_config', 'captcha_enabled')
