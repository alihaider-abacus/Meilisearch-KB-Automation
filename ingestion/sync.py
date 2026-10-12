from __future__ import annotations

from collections import Counter

from config.settings import settings
from ingestion.database import Database
from ingestion.meilisearch_client import MeilisearchClient
from ingestion.transform import transform_record
from ingestion.validate import validate_documents


class KnowledgeBaseSync:
    """Perform a complete PostgreSQL → Meilisearch synchronization."""

    def __init__(
        self,
        database: Database | None = None,
        search: MeilisearchClient | None = None,
    ) -> None:
        self.database = database or Database()
        self.search = search or MeilisearchClient()

    def run(
        self,
        clear_existing: bool = False,
    ) -> dict[str, int]:
        """Run a complete synchronization."""

        if not self.database.ping():
            raise RuntimeError(
                "PostgreSQL health check failed."
            )

        self.search.health()
        self.search.configure_index()

        if clear_existing:
            self.search.delete_all_documents()

        counts: Counter[str] = Counter()
        batch: list[dict] = []

        for source_table, row in self.database.iter_all():

            document = transform_record(
                source_table=source_table.name,
                row=row,
            )

            batch.append(
                document
            )

            counts[
                source_table.name
            ] += 1

            if len(batch) >= settings.ingestion_batch_size:
                self._index_batch(
                    batch
                )
                batch.clear()

        if batch:
            self._index_batch(
                batch
            )

        expected_count = sum(
            counts.values()
        )

        actual_count = (
            self.search.document_count()
        )

        if actual_count != expected_count:
            raise RuntimeError(
                "Synchronization verification failed. "
                f"Expected {expected_count} documents, "
                f"found {actual_count}."
            )

        return dict(counts)

    def _index_batch(
        self,
        batch: list[dict],
    ) -> None:
        """Validate and upsert a batch."""

        validate_documents(
            batch
        )

        self.search.add_documents(
            batch
        )