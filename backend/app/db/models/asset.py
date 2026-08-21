"""Asset (CMDB) models: group tree, hosts, credentials."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class AssetGroup(Base, TimestampMixin):
    __tablename__ = "asset_group"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0)
    remark: Mapped[str] = mapped_column(String(256), default="")

    roles: Mapped[list["Role"]] = relationship(
        secondary="role_host_group", back_populates="host_groups"
    )


class Host(Base, TimestampMixin):
    __tablename__ = "asset_host"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    hostname: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    os_type: Mapped[str] = mapped_column(String(16), default="linux")  # linux/windows
    os_version: Mapped[str] = mapped_column(String(128), default="")
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("asset_group.id"), index=True)
    env: Mapped[str] = mapped_column(String(16), default="prod")  # dev/test/prod
    tags: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    sensitivity_level: Mapped[str] = mapped_column(String(16), default="normal")  # normal/sensitive
    status: Mapped[str] = mapped_column(String(16), default="offline")  # online/offline
    connector: Mapped[str] = mapped_column(String(16), default="agent")  # agent/ssh
    agent_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    agent_version: Mapped[str] = mapped_column(String(32), default="")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str] = mapped_column(String(512), default="")
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    group: Mapped[AssetGroup | None] = relationship(lazy="joined")


class HostCredential(Base, TimestampMixin):
    __tablename__ = "host_credential"
    __table_args__ = (UniqueConstraint("host_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    host_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("asset_host.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(16), default="password")  # password/key
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # AES-GCM
    key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # AES-GCM private key
    key_version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
