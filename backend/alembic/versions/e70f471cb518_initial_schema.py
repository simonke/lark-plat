"""initial schema

Revision ID: e70f471cb518
Revises: 
Create Date: 2026-08-13 10:38:27.781768
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'e70f471cb518'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'asset_group',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('parent_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('remark', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asset_group_parent_id', 'asset_group', ['parent_id'], unique=False)

    op.create_table(
        'sys_user',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('password_hash', sa.String(length=256), nullable=False),
        sa.Column('real_name', sa.String(length=64), nullable=False),
        sa.Column('phone', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=128), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_admin', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sys_user_deleted', 'sys_user', ['deleted'], unique=False)
    op.create_index('ix_sys_user_username', 'sys_user', ['username'], unique=True)

    op.create_table(
        'sys_role',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('remark', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sys_role_code', 'sys_role', ['code'], unique=True)

    op.create_table(
        'sys_permission',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('parent_id', sa.BigInteger(), nullable=False),
        sa.Column('code', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('path', sa.String(length=256), nullable=False),
        sa.Column('icon', sa.String(length=64), nullable=False),
        sa.Column('sort', sa.Integer(), nullable=False),
        sa.Column('remark', sa.String(length=256), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sys_permission_code', 'sys_permission', ['code'], unique=True)

    op.create_table(
        'config_rule',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('rule_key', sa.String(length=64), nullable=False),
        sa.Column('rule_value', JSONB(), nullable=False),
        sa.Column('remark', sa.String(length=256), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_config_rule_rule_key', 'config_rule', ['rule_key'], unique=True)

    op.create_table(
        'sys_audit_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=True),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('module', sa.String(length=32), nullable=False),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('method', sa.String(length=8), nullable=False),
        sa.Column('path', sa.String(length=256), nullable=False),
        sa.Column('params', JSONB(), nullable=True),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('user_agent', sa.String(length=256), nullable=False),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('cost_ms', sa.Integer(), nullable=False),
        sa.Column('trace_id', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    for col in ('user_id', 'username', 'action', 'trace_id', 'module', 'ip'):
        op.create_index(f'ix_sys_audit_log_{col}', 'sys_audit_log', [col], unique=False)
    op.create_index('ix_sys_audit_log_created_at', 'sys_audit_log', ['created_at'], unique=False)

    op.create_table(
        'notify_channel',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('config_enc', sa.Text(), nullable=False),
        sa.Column('enabled', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'notify_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('channel_id', sa.BigInteger(), nullable=True),
        sa.Column('scene', sa.String(length=16), nullable=False),
        sa.Column('target', sa.String(length=256), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_notify_record_channel_id', 'notify_record', ['channel_id'], unique=False)

    op.create_table(
        'script',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('params_def', JSONB(), nullable=True),
        sa.Column('remark', sa.String(length=256), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_script_name', 'script', ['name'], unique=False)

    op.create_table(
        'approval_request',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('request_no', sa.String(length=32), nullable=False),
        sa.Column('biz_type', sa.String(length=16), nullable=False),
        sa.Column('biz_id', sa.BigInteger(), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('requester_id', sa.BigInteger(), nullable=False),
        sa.Column('sensitive_hit', sa.String(length=256), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('approver_role_id', sa.BigInteger(), nullable=True),
        sa.Column('approver_id', sa.BigInteger(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_approval_request_requester_id', 'approval_request', ['requester_id'], unique=False)
    op.create_index('ix_approval_request_biz_id', 'approval_request', ['biz_id'], unique=True)
    op.create_index('ix_approval_request_status', 'approval_request', ['status'], unique=False)
    op.create_index('ix_approval_request_request_no', 'approval_request', ['request_no'], unique=True)

    op.create_table(
        'approval_rule',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('value', JSONB(), nullable=False),
        sa.Column('trigger_action', sa.String(length=16), nullable=False),
        sa.Column('enabled', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'sys_user_role',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role_id'),
        sa.ForeignKeyConstraint(['user_id'], ['sys_user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['sys_role.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_sys_user_role_role_id', 'sys_user_role', ['role_id'], unique=False)
    op.create_index('ix_sys_user_role_user_id', 'sys_user_role', ['user_id'], unique=False)

    op.create_table(
        'sys_role_permission',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('permission_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'permission_id'),
        sa.ForeignKeyConstraint(['role_id'], ['sys_role.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['permission_id'], ['sys_permission.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_sys_role_permission_role_id', 'sys_role_permission', ['role_id'], unique=False)
    op.create_index('ix_sys_role_permission_permission_id', 'sys_role_permission', ['permission_id'], unique=False)

    op.create_table(
        'role_host_group',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('role_id', sa.BigInteger(), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('role_id', 'group_id'),
        sa.ForeignKeyConstraint(['role_id'], ['sys_role.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['asset_group.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_role_host_group_group_id', 'role_host_group', ['group_id'], unique=False)
    op.create_index('ix_role_host_group_role_id', 'role_host_group', ['role_id'], unique=False)

    op.create_table(
        'asset_host',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('hostname', sa.String(length=128), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('os_type', sa.String(length=16), nullable=False),
        sa.Column('os_version', sa.String(length=128), nullable=False),
        sa.Column('group_id', sa.BigInteger(), nullable=True),
        sa.Column('env', sa.String(length=16), nullable=False),
        sa.Column('tags', JSONB(), nullable=True),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('connector', sa.String(length=16), nullable=False),
        sa.Column('agent_id', sa.String(length=128), nullable=True),
        sa.Column('agent_version', sa.String(length=32), nullable=False),
        sa.Column('last_heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('remark', sa.String(length=512), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['group_id'], ['asset_group.id']),
    )
    op.create_index('ix_asset_host_agent_id', 'asset_host', ['agent_id'], unique=False)
    op.create_index('ix_asset_host_ip', 'asset_host', ['ip'], unique=True)
    op.create_index('ix_asset_host_hostname', 'asset_host', ['hostname'], unique=False)
    op.create_index('ix_asset_host_group_id', 'asset_host', ['group_id'], unique=False)

    op.create_table(
        'host_credential',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('host_id', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('secret_enc', sa.Text(), nullable=True),
        sa.Column('key_enc', sa.Text(), nullable=True),
        sa.Column('key_version', sa.Integer(), nullable=False),
        sa.Column('updated_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('host_id'),
        sa.ForeignKeyConstraint(['host_id'], ['asset_host.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_host_credential_host_id', 'host_credential', ['host_id'], unique=False)

    op.create_table(
        'script_version',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('script_id', sa.BigInteger(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('params_def', JSONB(), nullable=True),
        sa.Column('change_log', sa.String(length=512), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('script_id', 'version'),
        sa.ForeignKeyConstraint(['script_id'], ['script.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_script_version_script_id', 'script_version', ['script_id'], unique=False)

    op.create_table(
        'exec_task',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('task_no', sa.String(length=32), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('script_id', sa.BigInteger(), nullable=True),
        sa.Column('script_version', sa.Integer(), nullable=True),
        sa.Column('command', sa.Text(), nullable=True),
        sa.Column('params', JSONB(), nullable=True),
        sa.Column('target_host_ids', JSONB(), nullable=True),
        sa.Column('mode', sa.String(length=16), nullable=False),
        sa.Column('timeout_sec', sa.Integer(), nullable=False),
        sa.Column('retry', sa.Integer(), nullable=False),
        sa.Column('sensitive_flag', sa.Integer(), nullable=False),
        sa.Column('approve_required', sa.Integer(), nullable=False),
        sa.Column('approval_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['script_id'], ['script.id']),
    )
    op.create_index('ix_exec_task_status', 'exec_task', ['status'], unique=False)
    op.create_index('ix_exec_task_task_no', 'exec_task', ['task_no'], unique=True)
    op.create_index('ix_exec_task_created_by', 'exec_task', ['created_by'], unique=False)

    op.create_table(
        'schedule_task',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('script_id', sa.BigInteger(), nullable=True),
        sa.Column('command', sa.Text(), nullable=True),
        sa.Column('params', JSONB(), nullable=True),
        sa.Column('trigger_type', sa.String(length=16), nullable=False),
        sa.Column('cron_expr', sa.String(length=64), nullable=True),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.Column('interval_sec', sa.Integer(), nullable=True),
        sa.Column('target_host_ids', JSONB(), nullable=True),
        sa.Column('timeout_sec', sa.Integer(), nullable=False),
        sa.Column('retry', sa.Integer(), nullable=False),
        sa.Column('concurrency_limit', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.BigInteger(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['script_id'], ['script.id']),
    )
    op.create_index('ix_schedule_task_enabled', 'schedule_task', ['enabled'], unique=False)

    op.create_table(
        'approval_record',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('approval_id', sa.BigInteger(), nullable=False),
        sa.Column('action', sa.String(length=16), nullable=False),
        sa.Column('operator_id', sa.BigInteger(), nullable=False),
        sa.Column('comment', sa.String(length=512), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['approval_id'], ['approval_request.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_approval_record_approval_id', 'approval_record', ['approval_id'], unique=False)

    op.create_table(
        'exec_task_host',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('exec_task_id', sa.BigInteger(), nullable=False),
        sa.Column('host_id', sa.BigInteger(), nullable=False),
        sa.Column('hostname', sa.String(length=128), nullable=False),
        sa.Column('ip', sa.String(length=64), nullable=False),
        sa.Column('executor', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exec_task_id', 'host_id'),
        sa.ForeignKeyConstraint(['exec_task_id'], ['exec_task.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_exec_task_host_exec_task_id', 'exec_task_host', ['exec_task_id'], unique=False)
    op.create_index('ix_exec_task_host_host_id', 'exec_task_host', ['host_id'], unique=False)
    op.create_index('ix_exec_task_host_status', 'exec_task_host', ['status'], unique=False)

    op.create_table(
        'schedule_run',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('schedule_task_id', sa.BigInteger(), nullable=False),
        sa.Column('run_no', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('task_id', sa.BigInteger(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_no'),
        sa.ForeignKeyConstraint(['schedule_task_id'], ['schedule_task.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_schedule_run_schedule_task_id', 'schedule_run', ['schedule_task_id'], unique=False)

    op.create_table(
        'exec_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('task_host_id', sa.BigInteger(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('level', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_host_id', 'seq'),
        sa.ForeignKeyConstraint(['task_host_id'], ['exec_task_host.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_exec_log_task_host_id', 'exec_log', ['task_host_id'], unique=False)

    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_no_update() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'sys_audit_log is append-only: UPDATE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_log_no_delete() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'sys_audit_log is append-only: DELETE is forbidden';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_update BEFORE UPDATE ON sys_audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_no_update();"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_log_no_delete BEFORE DELETE ON sys_audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_no_delete();"
    )
    op.execute("REVOKE UPDATE, DELETE ON sys_audit_log FROM PUBLIC")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON sys_audit_log")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_update ON sys_audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_delete()")
    op.execute("DROP FUNCTION IF EXISTS audit_log_no_update()")

    op.drop_table('exec_log')
    op.drop_table('schedule_run')
    op.drop_table('exec_task_host')
    op.drop_table('approval_record')
    op.drop_table('schedule_task')
    op.drop_table('exec_task')
    op.drop_table('script_version')
    op.drop_table('host_credential')
    op.drop_table('asset_host')
    op.drop_table('role_host_group')
    op.drop_table('sys_role_permission')
    op.drop_table('sys_user_role')
    op.drop_table('approval_rule')
    op.drop_table('approval_request')
    op.drop_table('script')
    op.drop_table('notify_record')
    op.drop_table('notify_channel')
    op.drop_table('sys_audit_log')
    op.drop_table('config_rule')
    op.drop_table('sys_permission')
    op.drop_table('sys_role')
    op.drop_table('sys_user')
    op.drop_table('asset_group')
