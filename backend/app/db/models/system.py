"""System & auth models: user, role, permission, role_host_group (data permission)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    real_name: Mapped[str] = mapped_column(String(64), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    email: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 active / 0 disabled
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_admin: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    roles: Mapped[list["Role"]] = relationship(secondary="sys_user_role", back_populates="users")


class Role(Base, TimestampMixin):
    __tablename__ = "sys_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    remark: Mapped[str] = mapped_column(String(256), default="")

    users: Mapped[list[User]] = relationship(secondary="sys_user_role", back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(
        secondary="sys_role_permission", back_populates="roles"
    )
    host_groups: Mapped[list["AssetGroup"]] = relationship(
        secondary="role_host_group", back_populates="roles"
    )


class UserRole(Base):
    __tablename__ = "sys_user_role"
    __table_args__ = (UniqueConstraint("user_id", "role_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False, index=True
    )


class Permission(Base):
    __tablename__ = "sys_permission"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, default=0, nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), default="button")  # menu/button/action
    path: Mapped[str] = mapped_column(String(256), default="")
    icon: Mapped[str] = mapped_column(String(64), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str] = mapped_column(String(256), default="")

    roles: Mapped[list["Role"]] = relationship(
        secondary="sys_role_permission", back_populates="permissions"
    )


class RolePermission(Base):
    __tablename__ = "sys_role_permission"
    __table_args__ = (UniqueConstraint("role_id", "permission_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False, index=True
    )
    permission_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_permission.id", ondelete="CASCADE"), nullable=False, index=True
    )


class RoleHostGroup(Base):
    """Data permission: which host groups a role can operate on."""

    __tablename__ = "role_host_group"
    __table_args__ = (UniqueConstraint("role_id", "group_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sys_role.id", ondelete="CASCADE"), nullable=False, index=True
    )
    group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset_group.id", ondelete="CASCADE"), nullable=False, index=True
    )
