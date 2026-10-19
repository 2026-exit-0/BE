"""add ai_advices.report (structured report JSON)

Revision ID: c2d9e4a7f1b3
Revises: b7f3a2c91d84
Create Date: 2026-10-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d9e4a7f1b3'
down_revision: Union[str, None] = 'b7f3a2c91d84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_advices', sa.Column('report', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('ai_advices', 'report')
