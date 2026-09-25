"""Idempotent seed data: permission points, default roles, bootstrap admin.

Single source of truth for RBAC baseline:
- Permission codes match module-design v2.1 §13 (route → permission mapping) and
  api-design v2.1 §6.5 (terminal:*). Frontend v-perm / dynamic routes reference
  these codes directly, so any change here must be mirrored in the docs.
- Three default roles: admin (all perms), operator (operational), viewer (read-only).
- Bootstrap admin user: password only from SEED_ADMIN_PASSWORD env. In prod the
  user is skipped unless SEED_ADMIN_PASSWORD is explicitly set (fail-safe).

Run automatically on app startup (lifespan); also runnable via `python -m app.db.seed`.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import ConfigRule, Permission, Role, RolePermission, User, UserRole
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# (code, name, type, path, icon, children)
# child tuple: (code, name, type, path, icon)
PERMISSION_TREE: list[tuple[str, str, str, str, str, list[tuple[str, str, str, str, str]]]] = [
    ("dashboard:view", "仪表盘", "menu", "/dashboard", "Odometer", []),
    (
        "asset:host:list",
        "主机管理",
        "menu",
        "/assets/hosts",
        "Monitor",
        [
            ("asset:host:add", "新增主机", "button", "", "Plus"),
            ("asset:host:edit", "编辑主机", "button", "", "Edit"),
            ("asset:host:del", "删除主机", "button", "", "Delete"),
            ("asset:host:import", "批量导入", "button", "", "Upload"),
            ("asset:host:export", "导出", "button", "", "Download"),
            ("asset:host:conn", "连通性检测", "button", "", "Connection"),
            ("asset:host:executor", "执行器管理", "button", "", "Switch"),
        ],
    ),
    (
        "asset:group:list",
        "分组管理",
        "menu",
        "/assets/groups",
        "FolderOpened",
        [
            ("asset:group:add", "新增分组", "button", "", "Plus"),
            ("asset:group:edit", "编辑分组", "button", "", "Edit"),
            ("asset:group:del", "删除分组", "button", "", "Delete"),
        ],
    ),
    (
        "asset:cred:list",
        "凭据管理",
        "menu",
        "/assets/credentials",
        "Lock",
        [
            ("asset:cred:add", "新增凭据", "button", "", "Plus"),
            ("asset:cred:edit", "编辑凭据", "button", "", "Edit"),
        ],
    ),
    (
        "asset:relation:list",
        "CMDB 关系",
        "menu",
        "/assets/cmdb",
        "Share",
        [
            ("asset:relation:add", "新增关系", "button", "", "Plus"),
            ("asset:relation:del", "删除关系", "button", "", "Delete"),
            ("asset:topo:view", "拓扑/影响分析", "button", "", "Share"),
        ],
    ),
    (
        "workflow:list",
        "编排 Playbook",
        "menu",
        "/workflows",
        "Share",
        [
            ("workflow:add", "新增编排", "button", "", "Plus"),
            ("workflow:view", "查看编排", "button", "", "View"),
            ("workflow:edit", "编辑编排", "button", "", "Edit"),
            ("workflow:del", "删除编排", "button", "", "Delete"),
            ("workflow:version", "版本管理", "button", "", "Files"),
            ("workflow:rollback", "回滚版本", "button", "", "RefreshLeft"),
            ("workflow:run", "运行编排", "button", "", "VideoPlay"),
            ("workflow:cancel", "取消运行", "button", "", "CircleClose"),
        ],
    ),
    (
        "cicd:provider:list",
        "CI/CD 集成",
        "menu",
        "/cicd/providers",
        "Promotion",
        [
            ("cicd:provider:add", "新增接入", "button", "", "Plus"),
            ("cicd:provider:edit", "编辑接入", "button", "", "Edit"),
            ("cicd:provider:del", "删除接入", "button", "", "Delete"),
            ("cicd:provider:test", "连通测试", "button", "", "Connection"),
        ],
    ),
    (
        "release:list",
        "发布编排",
        "menu",
        "/releases",
        "Upload",
        [
            ("release:add", "创建发布", "button", "", "Plus"),
            ("release:view", "查看发布", "button", "", "View"),
            ("release:deploy", "开始部署", "button", "", "VideoPlay"),
            ("release:canary", "灰度放量", "button", "", "TrendCharts"),
            ("release:promote", "全量发布", "button", "", "Promotion"),
            ("release:fail", "标记失败", "button", "", "CircleClose"),
            ("release:rollback", "回滚", "button", "", "RefreshLeft"),
            ("release:cancel", "取消发布", "button", "", "CircleClose"),
        ],
    ),
    (
        "exec:task:list",
        "命令执行",
        "menu",
        "/exec/tasks",
        "Terminal",
        [
            ("exec:task:run", "执行任务", "button", "", "VideoPlay"),
            ("exec:task:stop", "终止任务", "button", "", "VideoPause"),
            ("exec:task:retry", "重试", "button", "", "Refresh"),
            ("exec:task:log", "实时回显", "button", "", "View"),
        ],
    ),
    (
        "transfer:package:list",
        "文件分发",
        "menu",
        "/transfer/tasks",
        "FolderOpened",
        [
            ("transfer:package:add", "新建包", "button", "", "Plus"),
            ("transfer:package:del", "删除包", "button", "", "Delete"),
            ("transfer:task:list", "任务列表", "button", "", "Tickets"),
            ("transfer:task:run", "分发任务", "button", "", "VideoPlay"),
            ("transfer:task:stop", "终止任务", "button", "", "VideoPause"),
            ("transfer:task:retry", "重试", "button", "", "Refresh"),
            ("transfer:task:log", "实时回显", "button", "", "View"),
        ],
    ),
    (
        "script:list",
        "脚本库",
        "menu",
        "/scripts",
        "Document",
        [
            ("script:add", "新增脚本", "button", "", "Plus"),
            ("script:edit", "编辑脚本", "button", "", "Edit"),
            ("script:del", "删除脚本", "button", "", "Delete"),
            ("script:version", "版本管理", "button", "", "Clock"),
            ("script:rollback", "版本回滚", "button", "", "Back"),
        ],
    ),
    (
        "schedule:list",
        "定时任务",
        "menu",
        "/schedules",
        "Timer",
        [
            ("schedule:add", "新增定时任务", "button", "", "Plus"),
            ("schedule:edit", "编辑定时任务", "button", "", "Edit"),
            ("schedule:del", "删除定时任务", "button", "", "Delete"),
            ("schedule:run", "立即执行", "button", "", "VideoPlay"),
            ("schedule:retry", "重试", "button", "", "Refresh"),
        ],
    ),
    (
        "approval:list",
        "审批中心",
        "menu",
        "/approvals",
        "Stamp",
        [
            ("approval:approve", "审批", "button", "", "Finished"),
            ("approval:request", "发起审批", "button", "", "Checked"),
        ],
    ),
    (
        "terminal:list",
        "Web 终端",
        "menu",
        "/terminals",
        "Cpu",
        [
            ("terminal:create", "新建会话", "button", "", "Plus"),
            ("terminal:close", "关闭会话", "button", "", "Close"),
            ("terminal:view", "查看会话", "button", "", "View"),
            ("terminal:replay", "回放录制", "button", "", "VideoPlay"),
        ],
    ),
    (
        "notify:channel:list",
        "通知渠道",
        "menu",
        "/notify/channels",
        "Bell",
        [
            ("notify:channel:add", "新增渠道", "button", "", "Plus"),
            ("notify:channel:edit", "编辑渠道", "button", "", "Edit"),
            ("notify:channel:del", "删除渠道", "button", "", "Delete"),
            ("notify:channel:test", "测试发送", "button", "", "Promotion"),
        ],
    ),
    ("notify:record:list", "发送记录", "menu", "/notify/records", "Memo", []),
    (
        "system:user:list",
        "用户管理",
        "menu",
        "/system/users",
        "User",
        [
            ("system:user:add", "新增用户", "button", "", "Plus"),
            ("system:user:edit", "编辑用户", "button", "", "Edit"),
            ("system:user:del", "删除用户", "button", "", "Delete"),
            ("system:user:role", "分配角色", "button", "", "Avatar"),
        ],
    ),
    (
        "system:role:list",
        "角色管理",
        "menu",
        "/system/roles",
        "UserFilled",
        [
            ("system:role:add", "新增角色", "button", "", "Plus"),
            ("system:role:edit", "编辑角色", "button", "", "Edit"),
            ("system:role:del", "删除角色", "button", "", "Delete"),
            ("system:role:perm", "分配权限", "button", "", "Key"),
            ("system:role:group", "数据权限", "button", "", "Share"),
        ],
    ),
    ("system:permission:list", "权限管理", "menu", "/system/permissions", "Grid", []),
    (
        "system:audit:list",
        "审计日志",
        "menu",
        "/system/audit-logs",
        "Notebook",
        [("system:audit:export", "导出", "button", "", "Download")],
    ),
    (
        "system:auth:provider",
        "身份集成",
        "menu",
        "/system/auth-providers",
        "Connection",
        [
            ("system:auth:provider:add", "新增身份源", "button", "", "Plus"),
            ("system:auth:provider:edit", "编辑身份源", "button", "", "Edit"),
            ("system:auth:provider:del", "删除身份源", "button", "", "Delete"),
            ("system:auth:provider:test", "连通测试", "button", "", "Promotion"),
        ],
    ),
    (
        "monitor:metric:view",
        "监控面板",
        "menu",
        "/monitor/dashboard",
        "Odometer",
        [],
    ),
    (
        "monitor:alert:list",
        "告警事件",
        "menu",
        "/monitor/alerts",
        "Bell",
        [
            ("monitor:alert:view", "查看详情", "button", "", "View"),
            ("monitor:alert:ack", "确认告警", "button", "", "Check"),
            ("monitor:alert:resolve", "解决告警", "button", "", "Finished"),
        ],
    ),
    (
        "monitor:rule:list",
        "告警规则",
        "menu",
        "/monitor/rules",
        "Setting",
        [
            ("monitor:rule:add", "新增规则", "button", "", "Plus"),
            ("monitor:rule:edit", "编辑规则", "button", "", "Edit"),
            ("monitor:rule:del", "删除规则", "button", "", "Delete"),
            ("monitor:rule:status", "启停规则", "button", "", "Switch"),
            ("monitor:rule:test", "测试连通", "button", "", "Connection"),
        ],
    ),
    (
        "ticket:list",
        "工单管理",
        "menu",
        "/tickets",
        "Tickets",
        [
            ("ticket:create", "创建工单", "button", "", "Plus"),
            ("ticket:edit", "编辑工单", "button", "", "Edit"),
            ("ticket:assign", "指派工单", "button", "", "User"),
            ("ticket:accept", "受理工单", "button", "", "Checked"),
            ("ticket:process", "处理工单", "button", "", "Loading"),
            ("ticket:done", "完成工单", "button", "", "Finished"),
            ("ticket:close", "关闭工单", "button", "", "Close"),
            ("ticket:reopen", "重新打开", "button", "", "Refresh"),
            ("ticket:cancel", "取消工单", "button", "", "CircleClose"),
            ("ticket:comment", "评论工单", "button", "", "ChatDotRound"),
            ("ticket:attachment", "上传附件", "button", "", "Paperclip"),
            ("ticket:ref", "关联对象", "button", "", "Link"),
        ],
    ),
    (
        "kb:article:list",
        "知识库",
        "menu",
        "/kb/articles",
        "Reading",
        [
            ("kb:article:add", "新增文章", "button", "", "Plus"),
            ("kb:article:edit", "编辑文章", "button", "", "Edit"),
            ("kb:article:del", "删除文章", "button", "", "Delete"),
            ("kb:article:version", "版本管理", "button", "", "Clock"),
            ("kb:article:rollback", "版本回滚", "button", "", "Back"),
            ("kb:category:list", "分类管理", "button", "", "FolderOpened"),
            ("kb:category:add", "新增分类", "button", "", "Plus"),
            ("kb:category:edit", "编辑分类", "button", "", "Edit"),
            ("kb:category:del", "删除分类", "button", "", "Delete"),
            ("kb:search", "知识检索", "button", "", "Search"),
        ],
    ),
    (
        "ai",
        "智能（AI）",
        "menu",
        "/ai",
        "MagicStick",
        [
            ("ai:use", "使用 AI", "button", "", "MagicStick"),
            ("ai:admin", "AI 治理", "button", "", "Setting"),
        ],
    ),
]

# role code -> permission codes
DEFAULT_ROLES: dict[str, dict[str, list[str]]] = {
    "admin": {
        "name": "系统管理员",
        "remark": "内置角色：全部权限（预置，勿删）",
        "permissions": [node[0] for node in PERMISSION_TREE]
        + [child[0] for node in PERMISSION_TREE for child in node[5]],
    },
    "operator": {
        "name": "运维操作员",
        "remark": "内置角色：日常运维操作权限",
        "permissions": [
            "dashboard:view",
            "asset:host:list", "asset:host:add", "asset:host:edit", "asset:host:import",
            "asset:host:export", "asset:host:conn", "asset:host:executor",
            "asset:group:list", "asset:group:add", "asset:group:edit",
            "asset:cred:list", "asset:cred:add", "asset:cred:edit",
            "exec:task:list", "exec:task:run", "exec:task:stop", "exec:task:retry", "exec:task:log",
            "transfer:package:list", "transfer:package:add", "transfer:package:del",
            "transfer:task:list", "transfer:task:run", "transfer:task:stop",
            "transfer:task:retry", "transfer:task:log",
            "script:list", "script:add", "script:edit", "script:version", "script:rollback",
            "schedule:list", "schedule:add", "schedule:edit", "schedule:del", "schedule:run", "schedule:retry",
            "approval:list", "approval:approve", "approval:request",
            "terminal:list", "terminal:create", "terminal:close", "terminal:view",
            "notify:record:list",
            "system:audit:list",
            "monitor:metric:view",
            "monitor:alert:list", "monitor:alert:view", "monitor:alert:ack", "monitor:alert:resolve",
            "monitor:rule:list", "monitor:rule:add", "monitor:rule:edit",
            "monitor:rule:status", "monitor:rule:test",
        ],
    },
    "viewer": {
        "name": "只读观察员",
        "remark": "内置角色：只读查看权限",
        "permissions": [
            "dashboard:view",
            "asset:host:list",
            "asset:group:list",
            "asset:cred:list",
            "exec:task:list", "exec:task:log",
            "transfer:package:list",
            "transfer:task:log",
            "script:list",
            "schedule:list",
            "approval:list",
            "terminal:list", "terminal:view",
            "notify:record:list",
            "system:audit:list",
            "monitor:metric:view",
            "monitor:alert:list", "monitor:alert:view",
            "monitor:rule:list",
        ],
    },
}


def _existing_codes(db: Session) -> set[str]:
    return set(db.scalars(select(Permission.code)).all())


def seed_permissions(db: Session) -> int:
    existing = _existing_codes(db)
    created = 0
    sort = 0
    for node in PERMISSION_TREE:
        code, name, ptype, path, icon, children = node
        if code not in existing:
            parent = Permission(
                parent_id=0, code=code, name=name, type=ptype,
                path=path, icon=icon, sort=sort,
            )
            db.add(parent)
            db.flush()
            created += 1
        else:
            parent = db.scalar(select(Permission).where(Permission.code == code))
        sort += 10
        for child in children:
            ccode, cname, ctype, cpath, cicon = child
            if ccode not in existing:
                db.add(
                    Permission(
                        parent_id=parent.id if parent else 0, code=ccode, name=cname,
                        type=ctype, path=cpath, icon=cicon, sort=sort,
                    )
                )
                created += 1
                sort += 10
    db.flush()
    return created


def seed_roles(db: Session) -> int:
    """Create/refresh default roles and bind their permission sets (idempotent)."""
    code_to_id = {
        code: pid
        for code, pid in db.execute(
            select(Permission.code, Permission.id)
        ).all()
    }
    touched = 0
    for rcode, spec in DEFAULT_ROLES.items():
        role = db.scalar(select(Role).where(Role.code == rcode))
        if role is None:
            role = Role(code=rcode, name=spec["name"], remark=spec["remark"])
            db.add(role)
            db.flush()
        else:
            role.name = spec["name"]
            role.remark = spec["remark"]
        want = {code_to_id[c] for c in spec["permissions"] if c in code_to_id}
        have = set(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role.id)).all())
        if want != have:
            db.execute(RolePermission.__table__.delete().where(RolePermission.role_id == role.id))
            db.add_all([RolePermission(role_id=role.id, permission_id=pid) for pid in want])
            touched += 1
    db.flush()
    return touched


def seed_bootstrap_users(db: Session) -> dict[str, bool]:
    """Create bootstrap admin/operator/viewer users bound to default roles (idempotent).

    prod: skipped unless SEED_ADMIN_PASSWORD is explicitly set (fail-safe).
    dev/test: falls back to documented defaults and logs a warning.
    Returns {username: created_or_bound}.
    """
    if settings.seed_admin_password:
        password = settings.seed_admin_password
        source = "env"
    elif settings.app_env != "prod":
        password = "admin@larkplat"
        source = "dev-default"
    else:
        logger.warning(
            "seed: SEED_ADMIN_PASSWORD not set in prod - skipping bootstrap users"
        )
        return {}

    specs = {
        "admin": ("系统管理员", 1, "admin"),
        "operator": ("运维操作员", 0, "operator"),
        "viewer": ("只读观察员", 0, "viewer"),
    }
    result: dict[str, bool] = {}
    for username, (real_name, is_admin, role_code) in specs.items():
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(
                username=username,
                password_hash=hash_password(password),
                real_name=real_name,
                status=1,
                is_admin=is_admin,
            )
            db.add(user)
            db.flush()
            result[username] = True
            logger.info("seed: bootstrap user '%s' created (password from %s)", username, source)
        role = db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            logger.warning("seed: role '%s' missing, skipping '%s' role binding", role_code, username)
        elif not db.scalar(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        ):
            db.add(UserRole(user_id=user.id, role_id=role.id))
            result[username] = result.get(username) or True
            logger.info("seed: bootstrap user '%s' bound to role '%s'", username, role_code)
    return result


def seed_admin_user(db: Session) -> bool:
    """Create bootstrap admin (is_admin=1) guarded by SEED_ADMIN_PASSWORD env.

    prod: skipped unless SEED_ADMIN_PASSWORD is explicitly set (fail-safe).
    dev/test: falls back to a documented default and logs a warning.

    Binds admin -> admin role (UserRole) so /auth/me returns roles + full
    permissions (60) per contract §2; is_admin=1 retained as bypass.
    Returns True if any row was created/bound.
    """
    username = "admin"
    if settings.seed_admin_password:
        password = settings.seed_admin_password
        source = "env"
    elif settings.app_env != "prod":
        password = "admin@larkplat"
        source = "dev-default"
    else:
        logger.warning(
            "seed: SEED_ADMIN_PASSWORD not set in prod - skipping bootstrap admin '%s'", username
        )
        return False

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(password),
            real_name="系统管理员",
            status=1,
            is_admin=1,
        )
        db.add(user)
        db.flush()
        logger.info("seed: bootstrap admin '%s' created (password from %s)", username, source)
        bind = True
    else:
        if not user.is_admin:
            user.is_admin = 1
        bind = False

    admin_role = db.scalar(select(Role).where(Role.code == "admin"))
    if admin_role is None:
        logger.warning("seed: admin role missing, skipping admin->admin role binding")
    elif not db.scalar(
        select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == admin_role.id)
    ):
        db.add(UserRole(user_id=user.id, role_id=admin_role.id))
        bind = True
        logger.info("seed: bootstrap admin '%s' bound to admin role", username)
    return bind


DEFAULT_CONFIG_RULES: dict[str, dict] = {
    # P2-MA O3/I2: sweep cadence + metric freshness defaults (never overwrite existing)
    "monitor.sweep_interval": {"seconds": 30},
    "monitor.metric_freshness_seconds": {"seconds": 300},
    # P2-3 SSO defaults (never overwrite existing)
    "sso.auto_provision": {"value": False},
    "sso.default_role_codes": {"value": []},
    # P2-SS executor extension (never overwrite existing)
    "executor.ssh_fallback": {"value": False},
    # P3 feature flags (never overwrite existing; default off)
    "feature.ticket": {"value": False},
    "feature.kb": {"value": False},
    "feature.cmdb_topology": {"value": False},
    "feature.workflow": {"value": False},
    "feature.cicd": {"value": False},
    # P4 (AIOps) feature flags (never overwrite existing; default off).
    "ai.enabled": {"value": False},
    "ai.events": {"value": False},
    "ai.ticket_assist": {"value": False},
    "ai.kb_assist": {"value": False},
    # P4 embedding-store selection (enum, not a boolean flag; default pg_array).
    "ai.embedding_store": {"value": "pg_array"},
}

_CONFIG_RULE_REMARKS: dict[str, str] = {
    "monitor.sweep_interval": "P2-MA default (O3/I2)",
    "monitor.metric_freshness_seconds": "P2-MA default (O3/I2)",
    "sso.auto_provision": "P2-3 SSO default",
    "sso.default_role_codes": "P2-3 SSO default",
    "executor.ssh_fallback": "P2-SS ssh 降级路由默认关闭",
    "feature.ticket": "P3-1 工单功能默认关闭",
    "feature.kb": "P3-2 知识库功能默认关闭",
    "feature.cmdb_topology": "P3-3 CMDB 深化（关系/拓扑/影响分析）默认关闭",
    "feature.workflow": "P3-4 编排 Playbook 默认关闭",
    "feature.cicd": "P3-5 CI/CD 集成（发布编排段）默认关闭",
    "ai.enabled": "P4 AI 能力总闸默认关闭",
    "ai.events": "P4 统一运维事件默认关闭",
    "ai.ticket_assist": "P4 工单助手默认关闭",
    "ai.kb_assist": "P4 KB-RAG 助手默认关闭",
    "ai.embedding_store": "P4 向量存储后端（pg_array|in_memory）",
}


def seed_config_rules(db: Session) -> int:
    created = 0
    for key, value in DEFAULT_CONFIG_RULES.items():
        if db.scalar(select(ConfigRule).where(ConfigRule.rule_key == key)) is None:
            db.add(ConfigRule(rule_key=key, rule_value=value, remark=_CONFIG_RULE_REMARKS.get(key, "")))
            created += 1
    return created


def run_seed(db: Session) -> dict:
    perms = seed_permissions(db)
    roles = seed_roles(db)
    users = seed_bootstrap_users(db)
    configs = seed_config_rules(db)
    admin = users.get("admin", False)
    db.commit()
    summary = {"permissions": perms, "roles_bound": roles, "admin_created": admin,
               "config_rules": configs, "users": users}
    if any(summary.values()):
        logger.info("seed: applied %s", summary)
    return summary


def main() -> None:
    db = SessionLocal()
    try:
        print(run_seed(db))
    finally:
        db.close()


if __name__ == "__main__":
    main()
