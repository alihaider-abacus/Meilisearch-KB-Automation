"""Data Ingestion Pipeline Module.

Extracts records from PostgreSQL tables, transforms them into the unified schema,
and ingests them into Meilisearch in batches for autonomous 1024D vectorization.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Automatically ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any, Dict
from config.settings import settings
from ingestion.database import Database, SOURCE_TABLES
from ingestion.meilisearch_client import MeilisearchClient
from ingestion.transform import transform_record
from ingestion.validate import validate_documents


def run_pipeline(
    batch_size: int = 200,
    clear_existing: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """Execute the full data extraction, transformation, and ingestion pipeline.

    Args:
        batch_size: Number of records to index per Meilisearch batch request.
        clear_existing: If True, purges existing index documents before ingesting.
        verbose: If True, prints formatted progress to terminal.

    Returns:
        dict with success status, counts per table, and total records indexed.
    """
    if verbose:
        print("=" * 65)
        print(" [PHASE 5] KNOWLEDGE BASE DATA INGESTION PIPELINE")
        print("=" * 65)
        print(f" [*] Source Database: {settings.db_name} (PostgreSQL on port {settings.db_port})")
        print(f" [*] Target Index:   {settings.meili_index_name} (Meilisearch)")
        print(f" [*] Batch Size:     {batch_size} records per batch")
        print("-" * 65)

    db = Database()
    client = MeilisearchClient()
    start_time = time.time()

    try:
        # 1. Reset existing documents if requested
        if clear_existing:
            if verbose:
                print(" [*] Preparing clean index (clearing existing documents)...")
            client.delete_all_documents()
            if verbose:
                print(" [✓] Index cleared.")

        # 2. Process each table
        table_counts: Dict[str, int] = {}
        total_ingested = 0

        for source_table in SOURCE_TABLES:
            if source_table.name in settings.excluded_kb_tables:
                continue

            table_total = db.count_table(source_table.name)
            if verbose:
                print(f" [*] Ingesting '{source_table.name}' ({table_total:,} records)...")

            table_processed = 0
            batch: list[dict[str, Any]] = []

            for row in db.iter_table(source_table.name, batch_size=batch_size):
                # Transform row into clean document (legacy embedding column is silently ignored)
                doc = transform_record(source_table=source_table.name, row=row)
                batch.append(doc)
                table_processed += 1

                if len(batch) >= batch_size:
                    validate_documents(batch)
                    client.add_documents(batch)
                    if verbose:
                        pct = (table_processed / table_total) * 100 if table_total else 100
                        print(f"     -> {source_table.name}: {table_processed:,}/{table_total:,} ({pct:.1f}%) indexed")
                    batch.clear()

            # Flush remaining documents in batch
            if batch:
                validate_documents(batch)
                client.add_documents(batch)
                if verbose:
                    print(f"     -> {source_table.name}: {table_processed:,}/{table_total:,} (100.0%) indexed")
                batch.clear()

            table_counts[source_table.name] = table_processed
            total_ingested += table_processed

        # 3. Verify total index count
        if verbose:
            print("-" * 65)
            print(" [*] Verifying indexed documents in Meilisearch...")

        # Allow Meilisearch a brief moment to finish updating stats
        time.sleep(2)
        indexed_count = client.document_count()
        elapsed = time.time() - start_time

        if verbose:
            print(f" [✓] Verification Complete: {indexed_count:,} documents in Meilisearch")
            print(f"     Total Ingestion Time: {elapsed:.2f} seconds")
            print("=" * 65)

        return {
            "success": True,
            "total_ingested": indexed_count,
            "table_breakdown": table_counts,
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as exc:
        if verbose:
            print(f" [X] Ingestion pipeline failed: {exc}")
            print("=" * 65)
        return {"success": False, "error": str(exc)}

    finally:
        client.close()


if __name__ == "__main__":
    result = run_pipeline(batch_size=200, clear_existing=True, verbose=True)
    sys.exit(0 if result["success"] else 1)