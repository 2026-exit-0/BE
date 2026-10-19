"""add user_surveys demographics (age_band, gender)

Revision ID: b7f3a2c91d84
Revises: 450d9e590416
Create Date: 2026-10-19 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f3a2c91d84'
down_revision: Union[str, None] = '450d9e590416'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_surveys', sa.Column('age_band', sa.String(length=10), nullable=True))
    op.add_column('user_surveys', sa.Column('gender', sa.String(length=10), nullable=True))


def downgrade() -> None:
    op.drop_column('user_surveys', 'gender')
    op.drop_column('user_surveys', 'age_band')
