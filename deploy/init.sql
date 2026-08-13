-- lark-plat database bootstrap (runs once on first postgres init)
-- Append-only audit functions. The blocking triggers + REVOKE are created by the
-- alembic migration (alembic/versions/*_initial_schema.py) after tables exist,
-- because init.sql runs before migrations. This keeps a fresh volume safe.

CREATE OR REPLACE FUNCTION audit_log_no_update() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'sys_audit_log is append-only: UPDATE is forbidden';
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION audit_log_no_delete() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'sys_audit_log is append-only: DELETE is forbidden';
END;
$$ LANGUAGE plpgsql;
