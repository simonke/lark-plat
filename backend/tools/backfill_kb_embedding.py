"""Backfill KB embeddings (P5 E3).

Re-ingests every `kb_article` current version through the SAME single write seam
(`kb_ingestion.ingest_article`) that live publication uses — so a backfill and a
live publish can never diverge. Idempotent: each article is replace-ingested.

Run (from the backend checkout, backend venv):
    python -m tools.backfill_kb_embedding
    # or: python tools/backfill_kb_embedding.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.db.models import KbArticle, KbArticleVersion  # noqa: E402
from app.services.kb_ingestion import ingest_article  # noqa: E402


def _current_version(db, article: KbArticle) -> KbArticleVersion | None:
    return db.scalar(
        select(KbArticleVersion).where(
            KbArticleVersion.article_id == article.id,
            KbArticleVersion.version == article.current_version,
        )
    )


def backfill(db) -> int:
    """Re-ingest every article; returns total chunks written (caller commits)."""
    total = 0
    for article in db.scalars(select(KbArticle)).all():
        total += ingest_article(db, article, _current_version(db, article))
    return total


def main() -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        chunks = backfill(db)
        db.commit()
        print({"articles": None, "chunks": chunks})
    finally:
        db.close()


if __name__ == "__main__":
    main()
