"""System management service: users, roles, permissions, audit logs."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import hash_password
from app.db.models import Permission, User, UserRole
from app.repositories import (
    AuditLogRepository,
    PermissionRepository,
    RoleRepository,
    UserRepository,
)
from app.schemas import system as sch

VALID_PERM_TYPES = ("menu", "button", "action")


# ---------------------------------------------------------------- users


def list_users(db: Session, username: str | None, real_name: str | None, status: int | None,
               role_id: int | None, page: int, size: int) -> dict:
    repo = UserRepository(db)
    rows, total = repo.search(username, real_name, status, role_id, page, size)
    users = [sch.UserOut.model_validate(u).model_dump() for u in rows]
    for u, row in zip(users, rows):
        u["role_ids"] = [ur.role_id for ur in _user_roles(db, row.id)]
    return {"list": users, "total": total, "page": page, "size": size}


def _user_roles(db: Session, user_id: int) -> list[UserRole]:
    return list(db.scalars(select(UserRole).where(UserRole.user_id == user_id)).all())


def create_user(db: Session, data: sch.UserCreate) -> int:
    repo = UserRepository(db)
    if repo.by_username(data.username):
        raise ConflictError("username already exists")
    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        real_name=data.real_name,
        phone=data.phone,
        email=data.email,
        status=data.status,
    )
    repo.add(user)
    db.flush()
    if data.role_ids:
        repo.set_user_roles(user.id, data.role_ids)
    db.commit()
    return user.id


def update_user(db: Session, user_id: int, data: sch.UserUpdate) -> None:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    for field in ("real_name", "phone", "email", "status"):
        val = getattr(data, field)
        if val is not None:
            setattr(user, field, val)
    db.commit()


def delete_user(db: Session, user_id: int, operator_id: int) -> None:
    if user_id == operator_id:
        raise BadRequestError("cannot delete yourself")
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    user.deleted = 1
    db.commit()


def set_user_roles(db: Session, user_id: int, role_ids: list[int]) -> None:
    repo = UserRepository(db)
    if repo.get(user_id) is None:
        raise NotFoundError("user not found")
    repo.set_user_roles(user_id, role_ids)
    db.commit()


def set_user_status(db: Session, user_id: int, status: int) -> None:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    user.status = status
    db.commit()


def reset_password(db: Session, user_id: int, password: str) -> None:
    repo = UserRepository(db)
    user = repo.get(user_id)
    if user is None:
        raise NotFoundError("user not found")
    user.password_hash = hash_password(password)
    db.commit()


# ---------------------------------------------------------------- roles


def list_roles(db: Session) -> list[dict]:
    roles = RoleRepository(db).list_all()
    out = []
    for r in roles:
        item = sch.RoleOut.model_validate(r).model_dump()
        item["permission_ids"] = _role_permission_ids(db, r.id)
        item["group_ids"] = _role_group_ids(db, r.id)
        out.append(item)
    return out


def _role_permission_ids(db: Session, role_id: int) -> list[int]:
    from app.db.models import RolePermission

    return list(db.scalars(select(RolePermission.permission_id).where(RolePermission.role_id == role_id)).all())


def _role_group_ids(db: Session, role_id: int) -> list[int]:
    from app.db.models import RoleHostGroup

    return list(db.scalars(select(RoleHostGroup.group_id).where(RoleHostGroup.role_id == role_id)).all())


def create_role(db: Session, data: sch.RoleCreate) -> int:
    repo = RoleRepository(db)
    if repo.by_code(data.code):
        raise ConflictError("role code already exists")
    role = repo.add(repo.model(code=data.code, name=data.name, remark=data.remark))
    db.flush()
    db.commit()
    return role.id


def update_role(db: Session, role_id: int, data: sch.RoleUpdate) -> None:
    repo = RoleRepository(db)
    role = repo.get(role_id)
    if role is None:
        raise NotFoundError("role not found")
    if data.name is not None:
        role.name = data.name
    if data.remark is not None:
        role.remark = data.remark
    db.commit()


def delete_role(db: Session, role_id: int) -> None:
    repo = RoleRepository(db)
    role = repo.get(role_id)
    if role is None:
        raise NotFoundError("role not found")
    user_count = db.scalar(select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)) or 0
    if user_count:
        raise ConflictError("role in use by users")
    db.delete(role)
    db.commit()


def set_role_permissions(db: Session, role_id: int, permission_ids: list[int]) -> None:
    repo = RoleRepository(db)
    if repo.get(role_id) is None:
        raise NotFoundError("role not found")
    repo.set_permissions(role_id, permission_ids)
    db.commit()


def set_role_groups(db: Session, role_id: int, group_ids: list[int]) -> None:
    repo = RoleRepository(db)
    if repo.get(role_id) is None:
        raise NotFoundError("role not found")
    repo.set_groups(role_id, group_ids)
    db.commit()


# ---------------------------------------------------------------- permissions


def permission_tree(db: Session) -> list[dict]:
    nodes = PermissionRepository(db).tree()
    by_id: dict[int, dict] = {}
    for n in nodes:
        by_id[n.id] = {**sch.PermissionNode.model_validate(n).model_dump(), "children": []}
    roots: list[dict] = []
    for n in nodes:
        item = by_id[n.id]
        if n.parent_id and n.parent_id in by_id:
            by_id[n.parent_id]["children"].append(item)
        else:
            roots.append(item)
    return roots


def seed_permissions(db: Session) -> int:
    """Idempotently seed default permission points (menu/action/button)."""
    repo = PermissionRepository(db)
    seeded = 0
    for code, name, ptype, parent_code in DEFAULT_PERMISSIONS:
        if repo.by_code(code):
            continue
        parent_id = 0
        if parent_code:
            parent = repo.by_code(parent_code)
            parent_id = parent.id if parent else 0
        repo.add(Permission(code=code, name=name, type=ptype, parent_id=parent_id))
        seeded += 1
    db.commit()
    return seeded


DEFAULT_PERMISSIONS: list[tuple[str, str, str, str | None]] = [
    ("dashboard:view", "仪表盘查看", "menu", None),
    ("asset:host:list", "主机列表", "action", None),
    ("asset:host:add", "新增主机", "action", "asset:host:list"),
    ("asset:host:edit", "编辑主机", "action", "asset:host:list"),
    ("asset:host:del", "删除主机", "action", "asset:host:list"),
    ("asset:host:import", "导入主机", "action", "asset:host:list"),
    ("asset:host:export", "导出主机", "action", "asset:host:list"),
    ("asset:host:conn", "连通性检测", "action", "asset:host:list"),
    ("asset:group:list", "分组列表", "action", None),
    ("asset:group:add", "新增分组", "action", "asset:group:list"),
    ("asset:group:edit", "编辑分组", "action", "asset:group:list"),
    ("asset:group:del", "删除分组", "action", "asset:group:list"),
    ("asset:cred:list", "凭据列表", "action", None),
    ("asset:cred:add", "新增凭据", "action", "asset:cred:list"),
    ("asset:cred:edit", "编辑凭据", "action", "asset:cred:list"),
    ("asset:cred:del", "删除凭据", "action", "asset:cred:list"),
    ("exec:task:list", "执行任务列表", "action", None),
    ("exec:task:run", "执行任务", "action", "exec:task:list"),
    ("exec:task:stop", "终止任务", "action", "exec:task:list"),
    ("exec:task:retry", "重试任务", "action", "exec:task:list"),
    ("exec:task:log", "查看执行日志", "action", "exec:task:list"),
    ("script:list", "脚本列表", "action", None),
    ("script:add", "新建脚本", "action", "script:list"),
    ("script:edit", "编辑脚本", "action", "script:list"),
    ("script:del", "删除脚本", "action", "script:list"),
    ("script:version", "版本管理", "action", "script:list"),
    ("script:rollback", "回滚脚本", "action", "script:list"),
    ("schedule:list", "定时任务列表", "action", None),
    ("schedule:add", "新建定时任务", "action", "schedule:list"),
    ("schedule:edit", "编辑定时任务", "action", "schedule:list"),
    ("schedule:del", "删除定时任务", "action", "schedule:list"),
    ("schedule:run", "立即执行", "action", "schedule:list"),
    ("schedule:retry", "重试", "action", "schedule:list"),
    ("approval:list", "审批列表", "action", None),
    ("approval:request", "发起审批", "action", "approval:list"),
    ("approval:approve", "审批操作", "action", "approval:list"),
    ("notify:channel:list", "通知渠道列表", "action", None),
    ("notify:channel:add", "新增渠道", "action", "notify:channel:list"),
    ("notify:channel:edit", "编辑渠道", "action", "notify:channel:list"),
    ("notify:channel:del", "删除渠道", "action", "notify:channel:list"),
    ("notify:channel:test", "测试发送", "action", "notify:channel:list"),
    ("notify:record:list", "发送记录", "action", None),
    ("system:user:list", "用户列表", "action", None),
    ("system:user:add", "新增用户", "action", "system:user:list"),
    ("system:user:edit", "编辑用户", "action", "system:user:list"),
    ("system:user:del", "删除用户", "action", "system:user:list"),
    ("system:user:role", "分配角色", "action", "system:user:list"),
    ("system:role:list", "角色列表", "action", None),
    ("system:role:add", "新增角色", "action", "system:role:list"),
    ("system:role:edit", "编辑角色", "action", "system:role:list"),
    ("system:role:del", "删除角色", "action", "system:role:list"),
    ("system:role:perm", "分配权限", "action", "system:role:list"),
    ("system:role:group", "分配主机组", "action", "system:role:list"),
    ("system:permission:list", "权限点列表", "action", None),
    ("system:audit:list", "审计日志", "action", None),
    ("system:audit:export", "审计导出", "action", "system:audit:list"),
]


# ---------------------------------------------------------------- audit


def list_audit_logs(db: Session, module: str | None, action: str | None, username: str | None,
                    ip: str | None, start, end, page: int, size: int) -> dict:
    repo = AuditLogRepository(db)
    filters = {"module": module, "action": action, "username": username, "ip": ip, "start": start, "end": end}
    rows, total = repo.search(filters, page, size)
    return {
        "list": [sch.AuditLogOut.model_validate(r).model_dump() for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


def audit_log_detail(db: Session, log_id: int) -> dict:
    repo = AuditLogRepository(db)
    row = repo.get(log_id)
    if row is None:
        raise NotFoundError("audit log not found")
    return sch.AuditLogOut.model_validate(row).model_dump()
