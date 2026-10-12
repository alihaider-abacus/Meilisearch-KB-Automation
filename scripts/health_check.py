from __future__ import annotations

from typing import Any

from config.settings import settings
from ingestion.database import Database
from ingestion.meilisearch_client import (
    MeilisearchClient,
)


def check_database(
    database: Database | None = None,
) -> dict[str, Any]:
    """Check PostgreSQL availability."""

    database = database or Database()

    try:
        ok = database.ping()

        return {
            "status": (
                "ok"
                if ok
                else "error"
            ),
            "database": settings.db_name,
        }

    except Exception as exc:
        return {
            "status": "error",
            "database": settings.db_name,
            "error": str(exc),
        }


def check_meilisearch(
    search: MeilisearchClient | None = None,
) -> dict[str, Any]:
    """Check Meilisearch availability."""

    search = (
        search
        or MeilisearchClient()
    )

    try:
        health = search.health()

        return {
            "status": "ok",
            "health": health,
            "index": settings.meili_index_name,
            "documents": search.document_count(),
        }

    except Exception as exc:
        return {
            "status": "error",
            "index": settings.meili_index_name,
            "error": str(exc),
        }

    finally:
        if search is not None:
            try:
                search.close()
            except Exception:
                pass