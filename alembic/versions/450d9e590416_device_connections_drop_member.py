"""add device_connections table, drop scan_sessions.member

Revision ID: 450d9e590416
Revises: 27f636c26897
Create Date: 2026-09-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '450d9e590416'
down_revision: Union[str, None] = '27f636c26897'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('device_connections',
    sa.Column('device_id', sa.String(length=50), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('connected_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('device_id')
    )
    op.drop_column('scan_sessions', 'member')


def downgrade() -> None:
    op.add_column('scan_sessions', sa.Column('member', sa.String(length=20), nullable=True))
    op.drop_table('device_connections')
