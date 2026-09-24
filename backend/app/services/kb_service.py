"""Knowledge-base service (P3-2): articles, append-only versions, category tree, search.

Frozen contract:
  - PUT creates a NEW version (never mutates an existing version row); rollback
    appends a new version copied from the target.
  - ``classified`` articles are filtered out of list/detail/search for non-admin.
  - deleting an article referenced by a ticket => 409 (ConflictError).
  - category depth > KB_CATEGORY_MAX_DEPTH => 422 (ValidationError); moving a
    category into itself/descendant is rejected.
  - feature flag ``feature.kb`` gates behavior (default False -> 400).
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import schemas
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, ValidationError
from app.db.models import KbArticle, KbArticleTag, KbArticleVersion, KbCategory, TicketRef
from app.db.models.kb import KB_VISIBILITIES
from app.repositories import ConfigRuleRepository

KB_CATEGORY_MAX_DEPTH = 3


def _require_feature(db: Session) -> None:
    rule = ConfigRuleRepository(db).by_key("feature.kb")
    value = (rule.rule_value or {}).get("value", False) if rule else False
    if not value:
        raise BadRequestError("feature disabled")


def _iso(value) -> str | None:
    return value.isoformat() if value else None


# =============================================================== categories


def _category_depth(db: Session, category_id: int) -> int:
    """Depth of a category (a root has depth 1); cycle-safe."""
    depth = 0
    cur = category_id
    seen: set[int] = set()
    while cur and cur != 0 and cur not in seen:
        seen.add(cur)
        cat = db.get(KbCategory, cur)
        if cat is None:
            break
        depth += 1
        cur = cat.parent_id
    return depth


def _is_descendant(db: Session, ancestor_id: int, node_id: int) -> bool:
    """True when node_id is ancestor_id or lives under it (cycle-safe)."""
    cur = node_id
    seen: set[int] = set()
    while cur and cur != 0 and cur not in seen:
        if cur == ancestor_id:
            return True
        seen.add(cur)
        cat = db.get(KbCategory, cur)
        if cat is None:
            return False
        cur = cat.parent_id
    return False


def _subtree_height(db: Session, category_id: int) -> int:
    """Max additional depth below category_id (0 for a leaf)."""
    children = db.scalars(
        select(KbCategory).where(KbCategory.parent_id == category_id)
    ).all()
    if not children:
        return 0
    return 1 + max(_subtree_height(db, c.id) for c in children)


def create_category(db: Session, user, data: schemas.KbCategoryCreate) -> dict:
    _require_feature(db)
    user.require_perm("kb:category:add")
    parent_id = data.parent_id or 0
    depth = 1
    if parent_id:
        if db.get(KbCategory, parent_id) is None:
            raise ValidationError(f"parent category not found: {parent_id}")
        depth = _category_depth(db, parent_id) + 1
    if depth > KB_CATEGORY_MAX_DEPTH:
        raise ValidationError(
            f"category depth {depth} exceeds max {KB_CATEGORY_MAX_DEPTH}"
        )
    category = KbCategory(parent_id=parent_id, name=data.name, sort=data.sort or 0,
                          created_by=user.id)
    db.add(category)
    db.commit()
    return {"id": category.id, "parent_id": category.parent_id, "name": category.name,
            "sort": category.sort}


def list_categories(db: Session, user) -> dict:
    _require_feature(db)
    user.require_perm("kb:category:list")
    rows = db.scalars(
        select(KbCategory).order_by(KbCategory.sort, KbCategory.id)
    ).all()
    nodes = {
        c.id: {"id": c.id, "parent_id": c.parent_id, "name": c.name, "sort": c.sort,
               "children": []}
        for c in rows
    }
    roots: list[dict] = []
    for c in rows:
        node = nodes[c.id]
        parent = nodes.get(c.parent_id)
        if c.parent_id and parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)
    return {"tree": roots, "total": len(rows)}


def update_category(db: Session, user, category_id: int, data: schemas.KbCategoryUpdate) -> dict:
    _require_feature(db)
    user.require_perm("kb:category:edit")
    category = db.get(KbCategory, category_id)
    if category is None:
        raise NotFoundError("category not found")
    if data.name is not None:
        category.name = data.name
    if data.sort is not None:
        category.sort = data.sort
    if data.parent_id is not None:
        new_parent = data.parent_id or 0
        if new_parent:
            if db.get(KbCategory, new_parent) is None:
                raise ValidationError(f"parent category not found: {new_parent}")
            if _is_descendant(db, category_id, new_parent):
                raise ValidationError("cannot move a category into itself or a descendant")
        depth = _category_depth(db, new_parent) + 1 if new_parent else 1
        if depth + _subtree_height(db, category_id) > KB_CATEGORY_MAX_DEPTH:
            raise ValidationError(
                f"category depth exceeds max {KB_CATEGORY_MAX_DEPTH}"
            )
        category.parent_id = new_parent
    db.commit()
    return {"id": category.id, "parent_id": category.parent_id, "name": category.name,
            "sort": category.sort}


def delete_category(db: Session, user, category_id: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:category:del")
    category = db.get(KbCategory, category_id)
    if category is None:
        raise NotFoundError("category not found")
    if db.scalar(select(func.count()).select_from(KbCategory)
                 .where(KbCategory.parent_id == category_id)):
        raise ConflictError("category has child categories")
    if db.scalar(select(func.count()).select_from(KbArticle)
                 .where(KbArticle.category_id == category_id)):
        raise ConflictError("category has articles")
    db.delete(category)
    db.commit()
    return {"id": category_id, "deleted": True}


# =============================================================== articles


def _get_article(db: Session, article_id: int) -> KbArticle:
    article = db.get(KbArticle, article_id)
    if article is None:
        raise NotFoundError("article not found")
    return article


def _visible(user, article: KbArticle) -> None:
    if article.visibility == "classified" and not user.is_admin:
        raise NotFoundError("article not found")


def _current_version(db: Session, article: KbArticle) -> KbArticleVersion | None:
    return db.scalar(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article.id,
            KbArticleVersion.version == article.current_version,
        )
    )


def _article_out(article: KbArticle) -> dict:
    return {
        "id": article.id,
        "title": article.title,
        "category_id": article.category_id,
        "visibility": article.visibility,
        "current_version": article.current_version,
        "author_id": article.author_id,
        "summary": article.summary,
        "created_at": _iso(article.created_at),
        "updated_at": _iso(article.updated_at),
    }


def create_article(db: Session, user, data: schemas.KbArticleCreate) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:add")
    if data.visibility not in KB_VISIBILITIES:
        raise ValidationError(f"invalid visibility: {data.visibility}")
    if data.category_id and db.get(KbCategory, data.category_id) is None:
        raise ValidationError(f"category not found: {data.category_id}")
    article = KbArticle(
        title=data.title,
        category_id=data.category_id,
        visibility=data.visibility,
        current_version=1,
        author_id=user.id,
        summary=data.summary or "",
    )
    db.add(article)
    db.flush()
    db.add(KbArticleVersion(
        article_id=article.id, version=1, title=article.title,
        content=data.content, change_log="initial", editor_id=user.id,
    ))
    for tag in data.tags or []:
        db.add(KbArticleTag(article_id=article.id, tag=tag))
    db.commit()
    return _article_out(article)


def list_articles(db: Session, user, filters: dict, page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:list")
    stmt = select(KbArticle)
    conds = []
    if filters.get("keyword"):
        conds.append(KbArticle.title.ilike(f"%{filters['keyword']}%"))
    if filters.get("category_id"):
        conds.append(KbArticle.category_id == filters["category_id"])
    if filters.get("visibility"):
        conds.append(KbArticle.visibility == filters["visibility"])
    if not user.is_admin:
        conds.append(KbArticle.visibility != "classified")
    if conds:
        stmt = stmt.where(*conds)
    if filters.get("tag"):
        stmt = stmt.join(KbArticleTag, KbArticleTag.article_id == KbArticle.id).where(
            KbArticleTag.tag == filters["tag"]
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(KbArticle.id.desc()).offset((page - 1) * size).limit(size)
    ).unique().all()
    return {"list": [_article_out(r) for r in rows], "total": int(total),
            "page": page, "size": size}


def get_article(db: Session, user, article_id: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:list")
    article = _get_article(db, article_id)
    _visible(user, article)
    version = _current_version(db, article)
    tags = db.scalars(
        select(KbArticleTag.tag).where(KbArticleTag.article_id == article.id)
    ).all()
    out = _article_out(article)
    out["content"] = version.content if version else ""
    out["tags"] = list(tags)
    return out


def update_article(db: Session, user, article_id: int, data: schemas.KbArticleUpdate) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:edit")
    article = _get_article(db, article_id)
    _visible(user, article)
    if data.visibility is not None and data.visibility not in KB_VISIBILITIES:
        raise ValidationError(f"invalid visibility: {data.visibility}")
    if data.category_id is not None and data.category_id and db.get(KbCategory, data.category_id) is None:
        raise ValidationError(f"category not found: {data.category_id}")
    current = _current_version(db, article)
    content = data.content if data.content is not None else (current.content if current else "")
    if data.title is not None:
        article.title = data.title
    if data.category_id is not None:
        article.category_id = data.category_id
    if data.visibility is not None:
        article.visibility = data.visibility
    if data.summary is not None:
        article.summary = data.summary
    new_version = article.current_version + 1
    article.current_version = new_version
    db.add(KbArticleVersion(
        article_id=article.id, version=new_version, title=article.title,
        content=content, change_log=data.change_log or "", editor_id=user.id,
    ))
    db.commit()
    return _article_out(article)


def delete_article(db: Session, user, article_id: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:del")
    article = _get_article(db, article_id)
    referenced = db.scalar(
        select(TicketRef).where(TicketRef.ref_type == "kb_article", TicketRef.ref_id == article_id)
    )
    if referenced is not None:
        raise ConflictError("article is referenced by a ticket")
    db.delete(article)
    db.commit()
    return {"id": article_id, "deleted": True}


def list_versions(db: Session, user, article_id: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:version")
    article = _get_article(db, article_id)
    _visible(user, article)
    rows = db.scalars(
        select(KbArticleVersion).where(KbArticleVersion.article_id == article_id)
        .order_by(KbArticleVersion.version.desc())
    ).all()
    return {
        "article_id": article_id,
        "current_version": article.current_version,
        "list": [
            {"id": v.id, "version": v.version, "title": v.title, "change_log": v.change_log,
             "editor_id": v.editor_id, "created_at": _iso(v.created_at)}
            for v in rows
        ],
    }


def get_version(db: Session, user, article_id: int, version: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:version")
    article = _get_article(db, article_id)
    _visible(user, article)
    row = db.scalar(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article_id, KbArticleVersion.version == version
        )
    )
    if row is None:
        raise NotFoundError("article version not found")
    return {"article_id": article_id, "version": row.version, "title": row.title,
            "content": row.content, "change_log": row.change_log,
            "editor_id": row.editor_id, "created_at": _iso(row.created_at)}


def rollback_article(db: Session, user, article_id: int, data: schemas.KbRollbackIn) -> dict:
    _require_feature(db)
    user.require_perm("kb:article:rollback")
    article = _get_article(db, article_id)
    _visible(user, article)
    target = db.scalar(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article_id,
            KbArticleVersion.version == data.version,
        )
    )
    if target is None:
        raise NotFoundError("article version not found")
    new_version = article.current_version + 1
    article.current_version = new_version
    db.add(KbArticleVersion(
        article_id=article.id, version=new_version, title=article.title,
        content=target.content, change_log=f"rollback to v{target.version}",
        editor_id=user.id,
    ))
    db.commit()
    return _article_out(article)


def search_articles(db: Session, user, q: str | None, page: int, size: int) -> dict:
    _require_feature(db)
    user.require_perm("kb:search")
    stmt = select(KbArticle).outerjoin(
        KbArticleVersion,
        (KbArticleVersion.article_id == KbArticle.id)
        & (KbArticleVersion.version == KbArticle.current_version),
    )
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(or_(KbArticle.title.ilike(like), KbArticleVersion.content.ilike(like)))
    if not user.is_admin:
        conds.append(KbArticle.visibility != "classified")
    if conds:
        stmt = stmt.where(*conds)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(KbArticle.id.desc()).offset((page - 1) * size).limit(size)
    ).unique().all()
    return {"list": [_article_out(r) for r in rows], "total": int(total),
            "page": page, "size": size}
