"""stage4 web terminal: terminal_session + terminal_recording_chunk

Revision ID: c4f7a1d20e91
Revises: a1c7e9d24b60
Create Date: 2026-08-31 10:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = 'c4f7a1d20e91'
down_revision = 'a1c7e9d24b60'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'terminal_session',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_no', sa.String(length=64), nullable=False),
        sa.Column('host_id', sa.BigInteger(), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('close_reason', sa.String(length=32), nullable=False),
        sa.Column('terminated_by', sa.BigInteger(), nullable=True),
        sa.Column('sensitive', sa.Integer(), nullable=False),
        sa.Column('approval_id', sa.BigInteger(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_sec', sa.Integer(), nullable=False),
        sa.Column('bytes_out', sa.BigInteger(), nullable=False),
        sa.Column('bytes_in', sa.BigInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['host_id'], ['asset_host.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_no'),
    )
    op.create_index('ix_terminal_session_session_no', 'terminal_session', ['session_no'])
    op.create_index('ix_terminal_session_host_id', 'terminal_session', ['host_id'])
    op.create_index('ix_terminal_session_user_id', 'terminal_session', ['user_id'])
    op.create_index('ix_terminal_session_status', 'terminal_session', ['status'])
    op.create_index('ix_terminal_session_approval_id', 'terminal_session', ['approval_id'])
    op.create_index('ix_terminal_host_status', 'terminal_session', ['host_id', 'status'])
    op.create_index('ix_terminal_user_status', 'terminal_session', ['user_id', 'status'])

    op.create_table(
        'terminal_recording_chunk',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.BigInteger(), nullable=False),
        sa.Column('offset', sa.BigInteger(), nullable=False),
        sa.Column('data_enc', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['terminal_session.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'offset'),
    )
    op.create_index('ix_terminal_recording_chunk_session_id', 'terminal_recording_chunk', ['session_id'])


def downgrade() -> None:
    op.drop_index('ix_terminal_recording_chunk_session_id', table_name='terminal_recording_chunk')
    op.drop_table('terminal_recording_chunk')
    op.drop_index('ix_terminal_user_status', table_name='terminal_session')
    op.drop_index('ix_terminal_host_status', table_name='terminal_session')
    op.drop_index('ix_terminal_session_approval_id', table_name='terminal_session')
    op.drop_index('ix_terminal_session_status', table_name='terminal_session')
    op.drop_index('ix_terminal_session_user_id', table_name='terminal_session')
    op.drop_index('ix_terminal_session_host_id', table_name='terminal_session')
    op.drop_index('ix_terminal_session_session_no', table_name='terminal_session')
    op.drop_table('terminal_session')
