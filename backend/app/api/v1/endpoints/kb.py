"""Knowledge-base endpoints (P3-2): articles/versions/rollback, categories, search.

Static segments register before `{id}` param segments. Feature-flag/permission
guards live in the service (routes stay registered so openapi keeps every key).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbDep, UserDep
from app.core.response import Result
from app import schemas
from app.services import kb_service

router = APIRouter(prefix="/kb", tags=["kb"])


@router.get("/articles", response_model=Result)
def list_articles(
    db: DbDep,
    user: UserDep,
    keyword: str | None = None,
    category_id: int | None = None,
    tag: str | None = None,
    visibility: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    filters = {"keyword": keyword, "category_id": category_id, "tag": tag,
               "visibility": visibility}
    return Result.ok(kb_service.list_articles(db, user, filters, page, size))


@router.post("/articles", response_model=Result)
def create_article(db: DbDep, user: UserDep, data: schemas.KbArticleCreate):
    return Result.ok(kb_service.create_article(db, user, data))


@router.get("/articles/{article_id}", response_model=Result)
def get_article(db: DbDep, user: UserDep, article_id: int):
    return Result.ok(kb_service.get_article(db, user, article_id))


@router.put("/articles/{article_id}", response_model=Result)
def update_article(db: DbDep, user: UserDep, article_id: int, data: schemas.KbArticleUpdate):
    return Result.ok(kb_service.update_article(db, user, article_id, data))


@router.delete("/articles/{article_id}", response_model=Result)
def delete_article(db: DbDep, user: UserDep, article_id: int):
    return Result.ok(kb_service.delete_article(db, user, article_id))


@router.get("/articles/{article_id}/versions", response_model=Result)
def list_versions(db: DbDep, user: UserDep, article_id: int):
    return Result.ok(kb_service.list_versions(db, user, article_id))


@router.get("/articles/{article_id}/versions/{version}", response_model=Result)
def get_version(db: DbDep, user: UserDep, article_id: int, version: int):
    return Result.ok(kb_service.get_version(db, user, article_id, version))


@router.post("/articles/{article_id}/rollback", response_model=Result)
def rollback_article(db: DbDep, user: UserDep, article_id: int, data: schemas.KbRollbackIn):
    return Result.ok(kb_service.rollback_article(db, user, article_id, data))


@router.get("/categories", response_model=Result)
def list_categories(db: DbDep, user: UserDep):
    return Result.ok(kb_service.list_categories(db, user))


@router.post("/categories", response_model=Result)
def create_category(db: DbDep, user: UserDep, data: schemas.KbCategoryCreate):
    return Result.ok(kb_service.create_category(db, user, data))


@router.put("/categories/{category_id}", response_model=Result)
def update_category(db: DbDep, user: UserDep, category_id: int, data: schemas.KbCategoryUpdate):
    return Result.ok(kb_service.update_category(db, user, category_id, data))


@router.delete("/categories/{category_id}", response_model=Result)
def delete_category(db: DbDep, user: UserDep, category_id: int):
    return Result.ok(kb_service.delete_category(db, user, category_id))


@router.get("/search", response_model=Result)
def search_articles(
    db: DbDep,
    user: UserDep,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return Result.ok(kb_service.search_articles(db, user, q, page, size))
