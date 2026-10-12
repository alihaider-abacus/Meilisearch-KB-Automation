from __future__ import annotations

import json
import logging
import time
from typing import Any

import psycopg2
from psycopg2.extras import LogicalReplicationConnection
from psycopg2.extras import REPLICATION_LOGICAL

from config.settings import settings
from ingestion.database import Database
from ingestion.meilisearch_client import MeilisearchClient
from ingestion.transform import transform_record
from ingestion.validate import validate_document


logger = logging.getLogger(__name__)


SUPPORTED_TABLES = {
    "articles_kb",
    "news_kb",
    "pages_kb",
    "services_kb",
}


class KnowledgeBaseCDC:
    """
    PostgreSQL logical-replication consumer.

    PostgreSQL is the source of truth.

    CDC events are used only to identify which source row changed.
    The complete current row is then re-read from PostgreSQL and
    transformed using the same pipeline as the full synchronization.
    """

    def __init__(
        self,
        database: Database | None = None,
        search: MeilisearchClient | None = None,
    ) -> None:
        self.database = database or Database()
        self.search = search or MeilisearchClient()

        self.replication_dsn = (
            f"host={settings.db_host} "
            f"port={settings.db_port} "
            f"dbname={settings.db_name} "
            f"user={settings.db_user} "
            f"password={settings.db_password}"
        )

    def run(self) -> None:
        """Start the CDC worker."""

        self.database.ping()
        self.search.health()
        self.search.configure_index()

        logger.info(
            "Government Knowledge Base CDC worker started."
        )

        while True:
            try:
                self._run_replication()

            except KeyboardInterrupt:
                logger.info(
                    "CDC worker stopped by user."
                )
                raise

            except Exception:
                logger.exception(
                    "CDC worker failed. Retrying in 5 seconds."
                )
                time.sleep(5)

    def _run_replication(self) -> None:
        """Open a logical-replication connection and consume changes."""

        connection = psycopg2.connect(
            self.replication_dsn,
            connection_factory=LogicalReplicationConnection,
        )

        cursor = connection.cursor()

        try:
            self._ensure_replication_slot(cursor)

            logger.info(
                "Starting PostgreSQL logical replication: "
                "slot=%s plugin=%s",
                settings.cdc_slot_name,
                settings.cdc_plugin,
            )

            cursor.start_replication(
                slot_name=settings.cdc_slot_name,
                slot_type=REPLICATION_LOGICAL,
                options={
                    "format-version": "2",
                    "include-xids": "false",
                    "include-timestamp": "true",
                    "pretty-print": "false",
                },
                decode=True,
                status_interval=10,
            )

            consumer = _ReplicationConsumer(
                worker=self,
            )

            cursor.consume_stream(
                consumer,
                keepalive_interval=10,
            )

        finally:
            try:
                cursor.close()
            finally:
                connection.close()

    def _ensure_replication_slot(
        self,
        cursor: Any,
    ) -> None:
        """Create the configured logical-replication slot if necessary."""

        cursor.execute(
            """
            SELECT 1
            FROM pg_replication_slots
            WHERE slot_name = %s
            """,
            (settings.cdc_slot_name,),
        )

        if cursor.fetchone():
            logger.info(
                "Logical replication slot already exists: %s",
                settings.cdc_slot_name,
            )
            return

        logger.info(
            "Creating logical replication slot: %s",
            settings.cdc_slot_name,
        )

        cursor.create_replication_slot(
            settings.cdc_slot_name,
            slot_type=REPLICATION_LOGICAL,
            output_plugin=settings.cdc_plugin,
        )

    def process_change(
        self,
        change: dict[str, Any],
    ) -> None:
        """
        Process one wal2json format-version 2 change.

        Format-version 2 uses:

            action: I / U / D
            table: table name

        INSERT/UPDATE records contain:

            columns: [
                {
                    "name": "...",
                    "type": "...",
                    "value": "..."
                }
            ]

        DELETE records contain:

            identity: [
                {
                    "name": "id",
                    "type": "text",
                    "value": "..."
                }
            ]

        Only the configured knowledge-base tables are synchronized.
        """

        table_name = change.get("table")

        if table_name not in SUPPORTED_TABLES:
            return

        action = change.get("action")

        logger.debug(
            "Processing CDC event: action=%s table=%s",
            action,
            table_name,
        )

        if action in {"I", "U"}:
            record_id = self._extract_id_from_columns(
                change.get("columns")
            )

            if not record_id:
                logger.warning(
                    "CDC %s event has no primary-key ID: %s",
                    action,
                    change,
                )
                return

            self._upsert_from_source(
                table_name=table_name,
                record_id=record_id,
            )
            return

        if action == "D":
            record_id = self._extract_delete_id(change)

            if not record_id:
                logger.warning(
                    "CDC delete event has no primary-key ID: %s",
                    change,
                )
                return

            document_id = self._document_id(
                table_name=table_name,
                record_id=record_id,
            )

            self.search.delete_document(document_id)

            logger.info(
                "Deleted Meilisearch document %s",
                document_id,
            )

            return

        # wal2json format-version 2 also emits transaction
        # boundary records such as B and C.
        #
        # They do not represent table changes and therefore
        # require no database or Meilisearch operation.
        if action in {"B", "C"}:
            return

        logger.debug(
            "Ignoring unsupported wal2json action=%r: %s",
            action,
            change,
        )

    def _upsert_from_source(
        self,
        *,
        table_name: str,
        record_id: str,
    ) -> None:
        """
        Re-read the changed PostgreSQL row and rebuild
        its search document.

        PostgreSQL remains authoritative for the complete row.
        """

        row = self.database.get_row(
            table_name,
            record_id,
        )

        if row is None:
            logger.warning(
                "Source row no longer exists: %s/%s. "
                "Deleting corresponding search document.",
                table_name,
                record_id,
            )

            self.search.delete_document(
                self._document_id(
                    table_name=table_name,
                    record_id=record_id,
                )
            )
            return

        document = transform_record(
            source_table=table_name,
            row=row,
        )

        validation = validate_document(document)

        if not validation.valid:
            raise ValueError(
                f"CDC document validation failed for "
                f"{table_name}/{record_id}: "
                + "; ".join(validation.errors)
            )

        self.search.add_documents([document])

        logger.info(
            "Upserted Meilisearch document for %s/%s",
            table_name,
            record_id,
        )

    @staticmethod
    def _extract_id_from_columns(
        columns: Any,
    ) -> str | None:
        """
        Extract the primary-key ID from wal2json format-version 2.

        Example:

            "columns": [
                {
                    "name": "id",
                    "type": "text",
                    "value": "..."
                }
            ]
        """

        if not isinstance(columns, list):
            return None

        for column in columns:
            if not isinstance(column, dict):
                continue

            if column.get("name") != "id":
                continue

            value = column.get("value")

            if value is not None:
                return str(value)

        return None

    @staticmethod
    def _extract_delete_id(
        change: dict[str, Any],
    ) -> str | None:
        """
        Extract the primary-key ID from a wal2json DELETE event.

        With the configured wal2json format-version 2, the actual
        DELETE structure observed from PostgreSQL is:

            "identity": [
                {
                    "name": "id",
                    "type": "text",
                    "value": "..."
                }
            ]

        Compatibility handling for other wal2json representations
        is retained below.
        """

        # Some configurations may provide columns on DELETE.
        record_id = KnowledgeBaseCDC._extract_id_from_columns(
            change.get("columns")
        )

        if record_id:
            return record_id

        # Actual format observed in this implementation:
        #
        # "identity": [
        #     {
        #         "name": "id",
        #         "type": "text",
        #         "value": "..."
        #     }
        # ]
        identity = change.get("identity")

        if isinstance(identity, list):
            for column in identity:
                if not isinstance(column, dict):
                    continue

                if column.get("name") != "id":
                    continue

                value = column.get("value")

                if value is not None:
                    return str(value)

        # Compatibility with dictionary-style identity/oldkeys.
        for key_name in ("oldkeys", "identity"):
            keys = change.get(key_name)

            if not isinstance(keys, dict):
                continue

            key_names = (
                keys.get("keynames")
                or keys.get("names")
                or []
            )

            key_values = (
                keys.get("keyvalues")
                or keys.get("values")
                or []
            )

            for index, name in enumerate(key_names):
                if name != "id":
                    continue

                if index >= len(key_values):
                    continue

                value = key_values[index]

                if value is not None:
                    return str(value)

        return None

    @staticmethod
    def _document_id(
        *,
        table_name: str,
        record_id: str,
    ) -> str:
        """Build the Meilisearch document ID."""

        safe_table = _sanitize_identifier(table_name)
        safe_record_id = _sanitize_identifier(record_id)

        return f"{safe_table}_{safe_record_id}"


def _sanitize_identifier(value: str) -> str:
    """Convert a value into a Meilisearch-safe identifier."""

    value = str(value).strip()

    sanitized = "".join(
        character
        if (
            character.isalnum()
            or character in {"-", "_"}
        )
        else "_"
        for character in value
    )

    sanitized = sanitized.strip("_")

    if not sanitized:
        raise ValueError(
            "Cannot build a valid Meilisearch document identifier."
        )

    return sanitized


class _ReplicationConsumer:
    """Adapter between psycopg2 replication messages and CDC."""

    def __init__(
        self,
        worker: KnowledgeBaseCDC,
    ) -> None:
        self.worker = worker

    def __call__(
        self,
        message: Any,
    ) -> None:
        """Consume one wal2json replication message."""

        if message.payload is None:
            message.cursor.send_feedback(
                flush_lsn=message.data_start,
            )
            return

        payload = message.payload

        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")

        data = json.loads(payload)

        # wal2json format-version 2 produces one top-level
        # action object per replication message.
        action = data.get("action")

        if action in {"I", "U", "D"}:
            self.worker.process_change(data)

        elif action in {"B", "C"}:
            # Transaction BEGIN/COMMIT markers.
            pass

        else:
            logger.debug(
                "Ignoring unknown wal2json message: %s",
                data,
            )

        # IMPORTANT:
        #
        # WAL is acknowledged only after the event has been
        # processed successfully.
        #
        # If process_change() raises an exception, execution
        # never reaches this line and PostgreSQL can replay
        # the unacknowledged event after reconnection.
        message.cursor.send_feedback(
            flush_lsn=message.data_start,
        )