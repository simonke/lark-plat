"""Knowledge-base (P3-2) request/response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- articles


class KbArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    category_id: int | None = None
    visibility: str = "internal"  # public/internal/classified
    content: str = Field(min_length=1)
    summary: str = ""
    tags: list[str] | None = None


class KbArticleUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)
    category_id: int | None = None
    visibility: str | None = None
    content: str | None = None
    summary: str | None = None
    change_log: str = ""


class KbRollbackIn(BaseModel):
    version: int = Field(ge=1)


class KbArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    category_id: int | None
    visibility: str
    current_version: int
    author_id: int | None
    summary: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class KbArticleVersionOut(BaseModel):
    id: int
    version: int
    title: str
    change_log: str
    editor_id: int | None
    created_at: datetime | None = None


class KbArticleDetail(KbArticleOut):
    content: str = ""
    tags: list[str] = []


# ---------------------------------------------------------------- categories


class KbCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    parent_id: int | None = 0
    sort: int = 0


class KbCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    parent_id: int | None = None
    sort: int | None = None


class KbCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    parent_id: int
    name: str
    sort: int


class KbSearchOut(BaseModel):
    list: list[KbArticleOut]
    total: int = 0
    page: int = 1
    size: int = 10
