"""add products.caution_ingredients / efficacy / full_ingredients

Revision ID: d4e8b1c0a2f5
Revises: c2d9e4a7f1b3
Create Date: 2026-10-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4e8b1c0a2f5'
down_revision: Union[str, None] = 'c2d9e4a7f1b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('caution_ingredients', sa.JSON(), nullable=True))
    op.add_column('products', sa.Column('efficacy', sa.JSON(), nullable=True))
    op.add_column('products', sa.Column('full_ingredients', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('products', 'full_ingredients')
    op.drop_column('products', 'efficacy')
    op.drop_column('products', 'caution_ingredients')
