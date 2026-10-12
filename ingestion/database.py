from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from config.settings import settings


@dataclass(frozen=True)
class SourceTable:
    """Definition of a knowledge-base source table."""

    name: str
    content_type: str


SOURCE_TABLES: tuple[SourceTable, ...] = (
    SourceTable("articles_kb", "article"),
    SourceTable("news_kb", "news"),
    SourceTable("pages_kb", "page"),
    SourceTable("services_kb", "service"),
)


SOURCE_TABLE_MAP: dict[str, SourceTable] = {
    table.name: table
    for table in SOURCE_TABLES
}


class Database:
    """Read-only PostgreSQL access layer."""

    def __init__(self) -> None:
        self.connection_string = (
            f"host={settings.db_host} "
            f"port={settings.db_port} "
            f"dbname={settings.db_name} "
            f"user={settings.db_user} "
            f"password={settings.db_password}"
        )

    def connect(self) -> psycopg.Connection:
        """Create a PostgreSQL connection."""

        return psycopg.connect(
            self.connection_string,
            row_factory=dict_row,
        )

    def ping(self) -> bool:
        """Check whether PostgreSQL is reachable."""

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() is not None

    def count_table(self, table_name: str) -> int:
        """Return the number of rows in a configured source table."""

        self._validate_table_name(table_name)

        query = sql.SQL(
            "SELECT COUNT(*) AS count "
            "FROM {}.{}"
        ).format(
            sql.Identifier(settings.kb_schema),
            sql.Identifier(table_name),
        )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                row = cursor.fetchone()

        return int(row["count"]) if row else 0

    def count_all(self) -> dict[str, int]:
        """Return row counts for all configured source tables."""

        counts: dict[str, int] = {}

        for source_table in SOURCE_TABLES:
            if source_table.name in settings.excluded_kb_tables:
                continue

            counts[source_table.name] = self.count_table(
                source_table.name
            )

        return counts

    def iter_table(
        self,
        table_name: str,
        batch_size: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream rows from a source table."""

        self._validate_table_name(table_name)

        if batch_size is None:
            batch_size = settings.ingestion_batch_size

        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")

        query = sql.SQL(
            """
            SELECT *
            FROM {}.{}
            ORDER BY id
            """
        ).format(
            sql.Identifier(settings.kb_schema),
            sql.Identifier(table_name),
        )

        with self.connect() as connection:
            with connection.cursor(
                name=f"kb_{table_name}",
                row_factory=dict_row,
            ) as cursor:
                cursor.execute(query)

                while True:
                    rows = cursor.fetchmany(batch_size)

                    if not rows:
                        break

                    for row in rows:
                        yield self._normalize_row(row)

    def iter_all(self) -> Iterator[tuple[SourceTable, dict[str, Any]]]:
        """Stream every record from every configured source table."""

        for source_table in SOURCE_TABLES:
            if source_table.name in settings.excluded_kb_tables:
                continue

            for row in self.iter_table(source_table.name):
                yield source_table, row

    def get_row(
        self,
        table_name: str,
        record_id: str,
    ) -> dict[str, Any] | None:
        """Fetch one source row by primary-key ID."""

        self._validate_table_name(table_name)

        query = sql.SQL(
            """
            SELECT *
            FROM {}.{}
            WHERE id = %s
            LIMIT 1
            """
        ).format(
            sql.Identifier(settings.kb_schema),
            sql.Identifier(table_name),
        )

        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (record_id,))
                row = cursor.fetchone()

        if row is None:
            return None

        return self._normalize_row(row)

    @staticmethod
    def source_table(
        table_name: str,
    ) -> SourceTable | None:
        """Return configured source-table metadata."""

        return SOURCE_TABLE_MAP.get(table_name)

    @staticmethod
    def _validate_table_name(table_name: str) -> None:
        """Reject arbitrary table names."""

        if table_name not in SOURCE_TABLE_MAP:
            raise ValueError(
                f"Unsupported source table: {table_name!r}"
            )

    @staticmethod
    def _normalize_row(
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize PostgreSQL-specific values."""

        normalized = dict(row)

        embedding = normalized.get("embedding")

        if embedding is not None:
            normalized["embedding"] = Database._parse_embedding(
                embedding
            )

        topics = normalized.get("topics")

        if topics is not None and isinstance(topics, str):
            try:
                normalized["topics"] = json.loads(topics)
            except json.JSONDecodeError:
                normalized["topics"] = []

        return normalized

    @staticmethod
    def _parse_embedding(value: Any) -> list[float]:
        """Convert a pgvector value into a Python float list."""

        if isinstance(value, list):
            return [float(item) for item in value]

        if isinstance(value, tuple):
            return [float(item) for item in value]

        if isinstance(value, str):
            stripped = value.strip()

            if not (
                stripped.startswith("[")
                and stripped.endswith("]")
            ):
                raise ValueError(
                    "Invalid pgvector string representation."
                )

            values = json.loads(stripped)

            if not isinstance(values, list):
                raise ValueError(
                    "pgvector value must decode to a list."
                )

            return [float(item) for item in values]

        try:
            return [float(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Unsupported embedding type: {type(value)!r}"
            ) from exc