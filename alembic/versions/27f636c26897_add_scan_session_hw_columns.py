"""add scan_session hw columns (source, device_id, member)

Revision ID: 27f636c26897
Revises: 0d474e35fd7a
Create Date: 2026-09-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '27f636c26897'
down_revision: Union[str, None] = '0d474e35fd7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('scan_sessions',
                  sa.Column('source', sa.String(length=20), server_default='web', nullable=False))
    op.add_column('scan_sessions', sa.Column('device_id', sa.String(length=50), nullable=True))
    op.add_column('scan_sessions', sa.Column('member', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('scan_sessions', 'member')
    op.drop_column('scan_sessions', 'device_id')
    op.drop_column('scan_sessions', 'source')
