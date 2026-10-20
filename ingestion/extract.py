from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from ingestion.database import Database, SourceTable


@dataclass(frozen=True)
class ExtractedRecord:
    """A single record extracted from a knowledge-base PostgreSQL table.
    
    The legacy embedding column is silently excluded; Meilisearch will
    autonomously vectorize this record downstream.
    """

    source_table: str
    content_type: str
    id: str
    slug: str | None
    title: str | None
    summary: str | None
    content: str | None
    agency_name: str | None
    published_at: datetime | None
    url: str | None
    form_url: str | None
    topics: Any


class KnowledgeBaseExtractor:
    """Extract records from configured PostgreSQL knowledge-base tables."""

    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()

    def extract_table(
        self,
        source_table: SourceTable,
    ) -> Iterator[ExtractedRecord]:
        """Extract all records from one configured source table."""
        for row in self.database.iter_table(source_table.name):
            yield self._build_record(
                source_table=source_table,
                row=row,
            )

    def extract_all(self) -> Iterator[ExtractedRecord]:
        """Extract records from every configured knowledge-base table."""
        for source_table, row in self.database.iter_all():
            yield self._build_record(
                source_table=source_table,
                row=row,
            )

    @staticmethod
    def _build_record(
        source_table: SourceTable,
        row: dict[str, Any],
    ) -> ExtractedRecord:
        """Convert a raw PostgreSQL row into an ExtractedRecord."""
        return ExtractedRecord(
            source_table=source_table.name,
            content_type=source_table.content_type,
            id=str(row["id"]),
            slug=_optional_string(row.get("slug")),
            title=_optional_string(row.get("title")),
            summary=_optional_string(row.get("summary")),
            content=_extract_content(row),
            agency_name=_optional_string(row.get("agency_name")),
            published_at=row.get("published_at"),
            url=_optional_string(row.get("url")),
            form_url=_optional_string(row.get("form_url")),
            topics=row.get("topics") or [],
        )


def _optional_string(value: Any) -> str | None:
    """Convert a value into a normalized optional string."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _extract_content(row: dict[str, Any]) -> str | None:
    """Extract raw content field from source row."""
    if row.get("body_html") is not None:
        return str(row["body_html"])

    if row.get("content") is not None:
        return str(row["content"])

    return None