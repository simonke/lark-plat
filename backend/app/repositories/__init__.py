"""Concrete repositories. Services depend on these interfaces; unit tests mock them."""

from __future__ import annotations

from typing import Any, Sequence

from sqlalchemy import String, delete, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ApprovalRecord,
    ApprovalRequest,
    ApprovalRule,
    AssetGroup,
    AuditLog,
    ConfigRule,
    ExecLog,
    ExecTask,
    ExecTaskHost,
    Host,
    HostCredential,
    NotifyChannel,
    NotifyRecord,
    Permission,
    Role,
    RoleHostGroup,
    RolePermission,
    ScheduleRun,
    ScheduleTask,
    Script,
    ScriptVersion,
    User,
    UserRole,
)
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def by_username(self, username: str) -> User | None:
        return self.session.scalar(select(User).where(User.username == username))

    def search(self, username: str | None, real_name: str | None, status: int | None,
               role_id: int | None, page: int, size: int) -> tuple[list[User], int]:
        stmt = select(User).where(User.deleted == 0)
        conds = []
        if username:
            conds.append(User.username.ilike(f"%{username}%"))
        if real_name:
            conds.append(User.real_name.ilike(f"%{real_name}%"))
        if status is not None:
            conds.append(User.status == status)
        if role_id:
            stmt = stmt.join(UserRole, UserRole.user_id == User.id).where(UserRole.role_id == role_id)
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(User.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)

    def delete_hard(self, user_id: int) -> None:
        self.session.execute(delete(User).where(User.id == user_id))

    def set_user_roles(self, user_id: int, role_ids: list[int]) -> None:
        self.session.execute(delete(UserRole).where(UserRole.user_id == user_id))
        for rid in set(role_ids):
            self.session.add(UserRole(user_id=user_id, role_id=rid))


class RoleRepository(BaseRepository[Role]):
    model = Role

    def by_code(self, code: str) -> Role | None:
        return self.session.scalar(select(Role).where(Role.code == code))

    def set_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        self.session.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
        for pid in set(permission_ids):
            self.session.add(RolePermission(role_id=role_id, permission_id=pid))

    def set_groups(self, role_id: int, group_ids: list[int]) -> None:
        self.session.execute(delete(RoleHostGroup).where(RoleHostGroup.role_id == role_id))
        for gid in set(group_ids):
            self.session.add(RoleHostGroup(role_id=role_id, group_id=gid))

    def visible_group_ids(self, role_ids: list[int]) -> list[int]:
        if not role_ids:
            return []
        rows = self.session.execute(
            select(RoleHostGroup.group_id).where(RoleHostGroup.role_id.in_(role_ids))
        ).all()
        return [r[0] for r in rows]


class PermissionRepository(BaseRepository[Permission]):
    model = Permission

    def by_code(self, code: str) -> Permission | None:
        return self.session.scalar(select(Permission).where(Permission.code == code))

    def codes_by_user(self, user_id: int) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return list(self.session.scalars(stmt).unique().all())

    def role_codes(self, role_id: int) -> list[str]:
        stmt = (
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return list(self.session.scalars(stmt).all())

    def tree(self) -> list[Permission]:
        return list(self.session.scalars(select(Permission).order_by(Permission.sort, Permission.id)).all())


class GroupRepository(BaseRepository[AssetGroup]):
    model = AssetGroup

    def children_count(self, group_id: int) -> int:
        return self.count(AssetGroup.parent_id == group_id)

    def host_count(self, group_id: int) -> int:
        return self.session.scalar(
            select(func.count()).select_from(Host).where(Host.group_id == group_id)
        ) or 0

    def all_tree(self) -> list[AssetGroup]:
        return list(self.session.scalars(select(AssetGroup).order_by(AssetGroup.sort, AssetGroup.id)).all())


class HostRepository(BaseRepository[Host]):
    model = Host

    def by_ip(self, ip: str) -> Host | None:
        return self.session.scalar(select(Host).where(Host.ip == ip))

    def search(self, filters: dict[str, Any], page: int, size: int) -> tuple[list[Host], int]:
        stmt = select(Host)
        conds = []
        for key in ("hostname", "ip", "os_type", "env", "status", "connector"):
            if filters.get(key):
                conds.append(getattr(Host, key).ilike(f"%{filters[key]}%") if key in ("hostname", "ip")
                            else getattr(Host, key) == filters[key])
        if filters.get("group_id"):
            conds.append(Host.group_id == filters["group_id"])
        if filters.get("group_ids") is not None:
            conds.append(Host.group_id.in_(filters["group_ids"]))
        if filters.get("tag"):
            conds.append(Host.tags.cast(String).ilike(f"%{filters['tag']}%"))
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(Host.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)

    def stats(self, group_ids: list[int] | None) -> dict[str, Any]:
        stmt = select(Host)
        if group_ids is not None:
            stmt = stmt.where(Host.group_id.in_(group_ids))
        rows = list(self.session.scalars(stmt).all())
        by_env: dict[str, int] = {}
        online = 0
        for h in rows:
            by_env[h.env] = by_env.get(h.env, 0) + 1
            if h.status == "online":
                online += 1
        return {"total": len(rows), "online": online, "offline": len(rows) - online, "by_env": by_env}


class CredentialRepository(BaseRepository[HostCredential]):
    model = HostCredential

    def by_host(self, host_id: int) -> HostCredential | None:
        return self.session.scalar(select(HostCredential).where(HostCredential.host_id == host_id))


class ScriptRepository(BaseRepository[Script]):
    model = Script

    def by_name(self, name: str) -> Script | None:
        return self.session.scalar(select(Script).where(Script.name == name))

    def referenced_count(self, script_id: int) -> int:
        task = self.session.scalar(
            select(func.count()).select_from(ExecTask).where(
                ExecTask.script_id == script_id, ExecTask.status.in_(("created", "awaiting_approval", "approved", "running"))
            )
        ) or 0
        sched = self.session.scalar(
            select(func.count()).select_from(ScheduleTask).where(ScheduleTask.script_id == script_id)
        ) or 0
        return int(task) + int(sched)

    def search(self, name: str | None, type_: str | None, page: int, size: int) -> tuple[list[Script], int]:
        stmt = select(Script)
        conds = []
        if name:
            conds.append(Script.name.ilike(f"%{name}%"))
        if type_:
            conds.append(Script.type == type_)
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(Script.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)


class ScriptVersionRepository(BaseRepository[ScriptVersion]):
    model = ScriptVersion

    def by_script_version(self, script_id: int, version: int) -> ScriptVersion | None:
        return self.session.scalar(
            select(ScriptVersion).where(ScriptVersion.script_id == script_id,
                                        ScriptVersion.version == version)
        )

    def list_versions(self, script_id: int) -> list[ScriptVersion]:
        return list(self.session.scalars(
            select(ScriptVersion).where(ScriptVersion.script_id == script_id)
            .order_by(ScriptVersion.version.desc())
        ).all())


class ExecTaskRepository(BaseRepository[ExecTask]):
    model = ExecTask

    def by_task_no(self, task_no: str) -> ExecTask | None:
        return self.session.scalar(select(ExecTask).where(ExecTask.task_no == task_no))

    def search(self, filters: dict[str, Any], page: int, size: int) -> tuple[list[ExecTask], int]:
        stmt = select(ExecTask)
        conds = []
        if filters.get("task_no"):
            conds.append(ExecTask.task_no.ilike(f"%{filters['task_no']}%"))
        if filters.get("name"):
            conds.append(ExecTask.name.ilike(f"%{filters['name']}%"))
        if filters.get("status"):
            conds.append(ExecTask.status == filters["status"])
        if filters.get("kind"):
            conds.append(ExecTask.kind == filters["kind"])
        if filters.get("created_by"):
            conds.append(ExecTask.created_by == filters["created_by"])
        if filters.get("start"):
            conds.append(ExecTask.created_at >= filters["start"])
        if filters.get("end"):
            conds.append(ExecTask.created_at <= filters["end"])
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(ExecTask.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)

    def optimistic_update(self, task_id: int, from_status: str, to_status: str, version: int) -> bool:
        """CAS update: status version++ only when current status+version match."""
        result = self.session.execute(
            ExecTask.__table__.update()
            .where(ExecTask.id == task_id, ExecTask.status == from_status, ExecTask.version == version)
            .values(status=to_status, version=version + 1)
        )
        return result.rowcount == 1


class ExecTaskHostRepository(BaseRepository[ExecTaskHost]):
    model = ExecTaskHost

    def by_task(self, task_id: int) -> list[ExecTaskHost]:
        return list(self.session.scalars(
            select(ExecTaskHost).where(ExecTaskHost.exec_task_id == task_id).order_by(ExecTaskHost.id)
        ).all())

    def by_id(self, task_host_id: int) -> ExecTaskHost | None:
        return self.session.get(ExecTaskHost, task_host_id)

    def stats(self, task_id: int) -> dict[str, int]:
        rows = self.session.execute(
            select(ExecTaskHost.status, func.count()).where(ExecTaskHost.exec_task_id == task_id)
            .group_by(ExecTaskHost.status)
        ).all()
        return {s: c for s, c in rows}

    def update_status(self, task_host_id: int, status: str, **fields) -> None:
        values = {"status": status, **fields}
        self.session.execute(
            ExecTaskHost.__table__.update().where(ExecTaskHost.id == task_host_id).values(**values)
        )


class ExecLogRepository(BaseRepository[ExecLog]):
    model = ExecLog

    def append(self, task_host_id: int, seq: int, level: str, content: str) -> None:
        self.session.add(ExecLog(task_host_id=task_host_id, seq=seq, level=level, content=content))

    def after_seq(self, task_host_id: int, after_seq: int, size: int) -> tuple[list[ExecLog], int]:
        stmt = select(ExecLog).where(ExecLog.task_host_id == task_host_id, ExecLog.seq > after_seq)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(stmt.order_by(ExecLog.seq.asc()).limit(size)).all()
        return list(rows), int(total)

    def max_seq(self, task_host_id: int) -> int:
        return int(self.session.scalar(
            select(func.max(ExecLog.seq)).where(ExecLog.task_host_id == task_host_id)
        ) or 0)


class ScheduleTaskRepository(BaseRepository[ScheduleTask]):
    model = ScheduleTask

    def enabled_tasks(self) -> list[ScheduleTask]:
        return list(self.session.scalars(select(ScheduleTask).where(ScheduleTask.enabled == 1)).all())


class ScheduleRunRepository(BaseRepository[ScheduleRun]):
    model = ScheduleRun

    def runs_of(self, schedule_id: int, page: int, size: int) -> tuple[list[ScheduleRun], int]:
        stmt = select(ScheduleRun).where(ScheduleRun.schedule_task_id == schedule_id)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(ScheduleRun.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)


class ApprovalRepository(BaseRepository[ApprovalRequest]):
    model = ApprovalRequest

    def by_biz(self, biz_type: str, biz_id: int) -> ApprovalRequest | None:
        return self.session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.biz_type == biz_type,
                                          ApprovalRequest.biz_id == biz_id)
        )

    def by_request_no(self, request_no: str) -> ApprovalRequest | None:
        return self.session.scalar(select(ApprovalRequest).where(ApprovalRequest.request_no == request_no))

    def pending_for_user(self, user_id: int, page: int, size: int) -> tuple[list[ApprovalRequest], int]:
        stmt = select(ApprovalRequest).where(ApprovalRequest.status == "pending")
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(ApprovalRequest.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)

    def search(self, filters: dict[str, Any], page: int, size: int) -> tuple[list[ApprovalRequest], int]:
        stmt = select(ApprovalRequest)
        conds = []
        if filters.get("status"):
            conds.append(ApprovalRequest.status == filters["status"])
        if filters.get("biz_type"):
            conds.append(ApprovalRequest.biz_type == filters["biz_type"])
        if filters.get("requester_id"):
            conds.append(ApprovalRequest.requester_id == filters["requester_id"])
        if filters.get("mine_todo"):
            conds.append(ApprovalRequest.status == "pending")
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(ApprovalRequest.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)

    def optimistic_update(self, approval_id: int, from_status: str, to_status: str, version: int) -> bool:
        result = self.session.execute(
            ApprovalRequest.__table__.update()
            .where(ApprovalRequest.id == approval_id,
                   ApprovalRequest.status == from_status,
                   ApprovalRequest.version == version)
            .values(status=to_status, version=version + 1)
        )
        return result.rowcount == 1


class ApprovalRuleRepository(BaseRepository[ApprovalRule]):
    model = ApprovalRule

    def enabled(self) -> list[ApprovalRule]:
        return list(self.session.scalars(
            select(ApprovalRule).where(ApprovalRule.enabled == 1)
        ).all())


class ApprovalRecordRepository(BaseRepository[ApprovalRecord]):
    model = ApprovalRecord

    def timeline(self, approval_id: int) -> list[ApprovalRecord]:
        return list(self.session.scalars(
            select(ApprovalRecord).where(ApprovalRecord.approval_id == approval_id)
            .order_by(ApprovalRecord.id.asc())
        ).all())


class NotifyChannelRepository(BaseRepository[NotifyChannel]):
    model = NotifyChannel


class NotifyRecordRepository(BaseRepository[NotifyRecord]):
    model = NotifyRecord

    def search(self, filters: dict[str, Any], page: int, size: int) -> tuple[list[NotifyRecord], int]:
        stmt = select(NotifyRecord)
        conds = []
        for key in ("channel_id", "scene", "status"):
            if filters.get(key):
                conds.append(getattr(NotifyRecord, key) == filters[key])
        if filters.get("start"):
            conds.append(NotifyRecord.created_at >= filters["start"])
        if filters.get("end"):
            conds.append(NotifyRecord.created_at <= filters["end"])
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(NotifyRecord.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)


class AuditLogRepository(BaseRepository[AuditLog]):
    model = AuditLog

    def search(self, filters: dict[str, Any], page: int, size: int) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        conds = []
        for key in ("module", "action", "username", "ip"):
            if filters.get(key):
                conds.append(getattr(AuditLog, key).ilike(f"%{filters[key]}%"))
        if filters.get("start"):
            conds.append(AuditLog.created_at >= filters["start"])
        if filters.get("end"):
            conds.append(AuditLog.created_at <= filters["end"])
        if conds:
            stmt = stmt.where(*conds)
        total = self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.session.scalars(
            stmt.order_by(AuditLog.id.desc()).offset((page - 1) * size).limit(size)
        ).all()
        return list(rows), int(total)


class ConfigRuleRepository(BaseRepository[ConfigRule]):
    model = ConfigRule

    def by_key(self, key: str) -> ConfigRule | None:
        return self.session.scalar(select(ConfigRule).where(ConfigRule.rule_key == key))


class PermissionTreeRepository(BaseRepository[Permission]):
    model = Permission

    def tree(self) -> list[Permission]:
        return list(self.session.scalars(select(Permission).order_by(Permission.sort, Permission.id)).all())
