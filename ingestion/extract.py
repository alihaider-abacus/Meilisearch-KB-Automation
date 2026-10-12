from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterator

from ingestion.database import Database, SourceTable


@dataclass(frozen=True)
class ExtractedRecord:
    """
    A single record extracted from a knowledge-base PostgreSQL table.

    This class intentionally contains source data only.

    Responsibilities of this layer:
    - Read records from PostgreSQL.
    - Preserve the existing database embedding.
    - Preserve source-specific fields.
    - Provide a consistent object for downstream transformation.

    Responsibilities NOT handled here:
    - Generating embeddings.
    - Calling Vertex AI.
    - Calling Meilisearch.
    - Converting HTML into search text.
    - Building the final Meilisearch document.
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
    embedding: list[float] | None


class KnowledgeBaseExtractor:
    """
    Extract records from the configured PostgreSQL knowledge-base tables.

    The extractor does not modify PostgreSQL.

    Existing embeddings are read from the `embedding` column and passed
    downstream unchanged.
    """

    def __init__(self, database: Database | None = None) -> None:
        self.database = database or Database()

    def extract_table(
        self,
        source_table: SourceTable,
    ) -> Iterator[ExtractedRecord]:
        """
        Extract all records from one configured source table.
        """
        for row in self.database.iter_table(source_table.name):
            yield self._build_record(
                source_table=source_table,
                row=row,
            )

    def extract_all(self) -> Iterator[ExtractedRecord]:
        """
        Extract records from every configured knowledge-base table.

        Excluded tables are handled by Database.iter_all().
        """
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
        """
        Convert a raw PostgreSQL row into an ExtractedRecord.

        No data enrichment or embedding generation happens here.
        """
        return ExtractedRecord(
            source_table=source_table.name,
            content_type=source_table.content_type,
            id=str(row["id"]),
            slug=_optional_string(row.get("slug")),
            title=_optional_string(row.get("title")),
            summary=_optional_string(row.get("summary")),
            content=_extract_content(row),
            agency_name=_optional_string(
                row.get("agency_name")
            ),
            published_at=row.get("published_at"),
            url=_optional_string(row.get("url")),
            form_url=_optional_string(
                row.get("form_url")
            ),
            topics=row.get("topics") or [],
            embedding=_copy_embedding(
                row.get("embedding")
            ),
        )


def _optional_string(value: Any) -> str | None:
    """
    Convert a value into a normalized optional string.

    Empty strings are represented as None.
    """
    if value is None:
        return None

    value = str(value).strip()
    return value or None


def _extract_content(row: dict[str, Any]) -> str | None:
    """
    Extract the appropriate raw content field from a source row.

    The source tables are not identical:

    articles_kb / news_kb / services_kb
        -> body_html

    pages_kb
        -> content

    HTML is intentionally NOT converted to plain text here.
    HTML processing belongs to the transformation layer.
    """
    if row.get("body_html") is not None:
        return str(row["body_html"])

    if row.get("content") is not None:
        return str(row["content"])

    return None


def _copy_embedding(value: Any) -> list[float] | None:
    """
    Return a safe Python list copy of an existing database embedding.

    The embedding is NOT generated here.

    PostgreSQL/pgvector values are already normalized by
    Database._normalize_row(), so this function mainly protects
    the extracted record from accidental mutation.
    """
    if value is None:
        return None

    if not isinstance(value, (list, tuple)):
        raise TypeError(
            "Expected embedding to be a list or tuple, "
            f"got {type(value).__name__}"
        )

    return [float(item) for item in value]
