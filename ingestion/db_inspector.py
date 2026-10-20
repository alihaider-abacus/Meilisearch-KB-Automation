"""Database Inspector Module.

Connects to the PostgreSQL database in Docker, verifies connectivity,
and displays a clean table of KB tables and row counts.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Automatically ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any, Dict
from config.settings import settings
from ingestion.database import Database, SOURCE_TABLES


def inspect_database(verbose: bool = True) -> Dict[str, Any]:
    """Connect to the database and inspect knowledge-base tables.

    Returns:
        dict with connection status, per-table row counts, and total records.
    """
    db = Database()

    if verbose:
        print("=" * 65)
        print(" [PHASE 2] DATABASE INSPECTION & RECORD COUNTS")
        print("=" * 65)

    # 1. Test database connection
    try:
        is_connected = db.ping()
    except Exception as exc:
        if verbose:
            print(f" [X] Failed to connect to database: {exc}")
            print("     Make sure your Docker PostgreSQL container is running on port 5432.")
            print("=" * 65)
        return {"connected": False, "total_records": 0, "tables": {}}

    if not is_connected:
        if verbose:
            print(" [X] Database ping failed.")
            print("=" * 65)
        return {"connected": False, "total_records": 0, "tables": {}}

    if verbose:
        print(f" [✓] Connected successfully to database: {settings.db_name}")
        print(f"     Target Host: {settings.db_host}:{settings.db_port} (User: {settings.db_user})")
        print("-" * 65)
        print(f" {'Table Name':<20} {'Content Type':<15} {'Record Count':>15}")
        print("-" * 65)

    # 2. Inspect each configured knowledge-base table
    table_counts: Dict[str, int] = {}
    total_records = 0

    for source_table in SOURCE_TABLES:
        if source_table.name in settings.excluded_kb_tables:
            continue

        try:
            count = db.count_table(source_table.name)
            table_counts[source_table.name] = count
            total_records += count

            if verbose:
                print(f" {source_table.name:<20} {source_table.content_type:<15} {count:>15,}")
        except Exception as exc:
            if verbose:
                print(f" {source_table.name:<20} {'ERROR':<15} {str(exc):>15}")

    if verbose:
        print("-" * 65)
        print(f" {'Total Records to Ingest:':<36} {total_records:>15,}")
        print("=" * 65)

    return {
        "connected": True,
        "database": settings.db_name,
        "total_records": total_records,
        "tables": table_counts,
    }


if __name__ == "__main__":
    result = inspect_database(verbose=True)
    sys.exit(0 if result["connected"] else 1)