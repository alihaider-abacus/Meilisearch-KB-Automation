from __future__ import annotations

import re
from typing import Any

import httpx
import meilisearch

from config.settings import settings
from meili_config.index_config import INDEX_SETTINGS


class MeilisearchClient:
    """Client used by the ingestion layer to manage Meilisearch."""

    def __init__(self) -> None:
        self.client = meilisearch.Client(
            settings.meili_host,
            settings.meili_master_key,
        )

        self.http = httpx.Client(
            base_url=settings.meili_host.rstrip("/"),
            headers={
                "Authorization": (
                    f"Bearer {settings.meili_master_key}"
                ),
                "Content-Type": "application/json",
            },
            timeout=settings.meili_timeout_seconds,
        )

    def close(self) -> None:
        """Close HTTP resources."""
        self.http.close()

    def health(self) -> dict[str, Any]:
        """Return Meilisearch health information."""
        return self.client.health()

    def _wait_for_task(self, task: Any) -> Any:
        """Wait for a Meilisearch task to finish."""

        task_uid = getattr(
            task,
            "task_uid",
            None,
        )

        if task_uid is None:
            raise RuntimeError(
                "Meilisearch did not return a task UID."
            )

        result = self.client.wait_for_task(
            task_uid
        )

        status = getattr(
            result,
            "status",
            None,
        )

        if status == "failed":
            error = getattr(
                result,
                "error",
                None,
            )

            raise RuntimeError(
                f"Meilisearch task {task_uid} failed: {error}"
            )

        return result

    def get_or_create_index(self) -> Any:
        """Get the configured index or create it."""

        try:
            return self.client.get_index(
                settings.meili_index_name
            )

        except Exception as exc:
            error_text = str(exc).lower()

            error_code = str(
                getattr(
                    exc,
                    "code",
                    "",
                )
            ).lower()

            status_code = getattr(
                exc,
                "status_code",
                None,
            )

            is_not_found = (
                "index_not_found" in error_text
                or "index_not_found" in error_code
                or "not found" in error_text
                or status_code == 404
                or "404" in error_text
            )

            if not is_not_found:
                raise

        task = self.client.create_index(
            settings.meili_index_name,
            {
                "primaryKey": "id"
            },
        )

        self._wait_for_task(task)

        return self.client.index(
            settings.meili_index_name
        )

    def configure_index(self) -> None:
        """Apply the complete Government KB index configuration."""

        index = self.get_or_create_index()

        task = index.update_settings(
            INDEX_SETTINGS
        )

        self._wait_for_task(task)

    @staticmethod
    def _normalize_document_id(
        original_id: Any,
    ) -> str:
        """Convert a source ID into a safe Meilisearch ID."""

        if original_id is None:
            raise ValueError(
                "Cannot index a document without an 'id' field."
            )

        original_id = str(
            original_id
        )

        safe_id = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            original_id,
        )

        if not safe_id:
            raise ValueError(
                f"Document ID {original_id!r} "
                "is empty after normalization."
            )

        if len(
            safe_id.encode("utf-8")
        ) > 511:
            raise ValueError(
                f"Document ID {original_id!r} "
                "exceeds 511 bytes."
            )

        return safe_id

    def add_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> None:
        """Insert or update documents in Meilisearch."""

        if not documents:
            return

        normalized_documents: list[
            dict[str, Any]
        ] = []

        for document in documents:
            item = dict(
                document
            )

            original_id = item.get(
                "id"
            )

            item.setdefault(
                "source_id",
                (
                    str(original_id)
                    if original_id is not None
                    else None
                ),
            )

            item["id"] = (
                self._normalize_document_id(
                    original_id
                )
            )

            normalized_documents.append(
                item
            )

        index = self.client.index(
            settings.meili_index_name
        )

        task = index.add_documents(
            normalized_documents,
            primary_key="id",
        )

        self._wait_for_task(task)

    def delete_document(
        self,
        document_id: str,
    ) -> None:
        """Delete one document."""

        safe_id = (
            self._normalize_document_id(
                document_id
            )
        )

        index = self.client.index(
            settings.meili_index_name
        )

        task = index.delete_document(
            safe_id
        )

        self._wait_for_task(task)

    def delete_all_documents(self) -> None:
        """Delete all indexed documents."""

        index = self.client.index(
            settings.meili_index_name
        )

        task = (
            index.delete_all_documents()
        )

        self._wait_for_task(task)

    def document_count(self) -> int:
        """Return the number of indexed documents."""

        index = self.client.index(
            settings.meili_index_name
        )

        stats = index.get_stats()

        return int(
            stats.number_of_documents
        )