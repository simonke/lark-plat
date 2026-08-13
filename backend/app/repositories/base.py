"""Generic repository base. Services depend on repository interfaces (not Session),
so unit tests can inject mocks (design §5: test-friendly)."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base

M = TypeVar("M", bound=Base)


class BaseRepository(Generic[M]):
    """Thin generic CRUD over a session. Concrete repos subclass for query logic."""

    model: type[M]

    def __init__(self, session: Session):
        self.session = session

    def add(self, obj: M) -> M:
        self.session.add(obj)
        return obj

    def get(self, id: int) -> M | None:
        return self.session.get(self.model, id)

    def list_all(self) -> list[M]:
        return list(self.session.scalars(select(self.model)).all())

    def delete(self, obj: M) -> None:
        self.session.delete(obj)

    def flush(self) -> None:
        self.session.flush()

    def count(self, *where: Any) -> int:
        stmt = select(func.count(self.model.id))
        if where:
            stmt = stmt.where(*where)
        return int(self.session.scalar(stmt) or 0)
