"""add product terms field

Revision ID: 0049ac7e24ac
Revises: d4e5f6a7b8c9
Create Date: 2026-06-28 02:34:21.566847
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0049ac7e24ac'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 仅添加 product.terms 字段（autogenerate 误识别的索引删除已剔除）
    op.add_column('product', sa.Column('terms', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('product', 'terms')
