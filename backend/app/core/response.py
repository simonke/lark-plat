"""Unified response envelope and error codes.

Contract (api-design v2.0 §1):
  success -> {"code": 0, "message": "ok", "data": ...}
  error   -> {"code": <code>, "message": "...", "data": null}
  pagination data -> {"list": [], "total": 0, "page": 1, "size": 10}
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# Error codes
CODE_OK = 0
CODE_BAD_REQUEST = 400
CODE_UNAUTHORIZED = 401
CODE_FORBIDDEN = 403
CODE_NOT_FOUND = 404
CODE_CONFLICT = 409
CODE_UNPROCESSABLE = 422
CODE_TOO_MANY = 429
CODE_SERVER_ERROR = 500
CODE_BUSINESS = 1001

T = TypeVar("T")


class Result(BaseModel, Generic[T]):
    code: int = CODE_OK
    message: str = "ok"
    data: T | None = None

    @classmethod
    def ok(cls, data: Any = None, message: str = "ok") -> "Result":
        return cls(code=CODE_OK, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> "Result":
        return cls(code=code, message=message, data=data)


class PageVO(BaseModel, Generic[T]):
    model_config = ConfigDict(populate_by_name=True)

    items: list[T] = Field(default_factory=list, alias="list")
    total: int = 0
    page: int = 1
    size: int = 10

    @classmethod
    def build(cls, items: list[T], total: int, page: int, size: int) -> "PageVO[T]":
        return cls(items=items, total=total, page=page, size=size)
