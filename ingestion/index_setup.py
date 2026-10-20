"""Index Setup Module.

Applies index configuration, searchable/filterable attributes, and 1024D
Gemini REST embedder settings to Meilisearch.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any, Dict
from config.settings import settings
from meili_config.index_config import get_index_settings
from ingestion.meilisearch_client import MeilisearchClient


def setup_meilisearch_index(reset: bool = False, verbose: bool = True) -> Dict[str, Any]:
    """Create or update the Meilisearch index with 1024D Gemini embedder settings.

    Args:
        reset: If True, deletes existing documents in the index before applying settings.
        verbose: If True, prints formatted progress to terminal.

    Returns:
        dict with success status and details.
    """
    if verbose:
        print("=" * 65)
        print(" [PHASE 4] MEILISEARCH 1024D EMBEDDER & INDEX CONFIGURATION")
        print("=" * 65)

    client = MeilisearchClient()

    try:
        # 1. Get or create index
        index = client.get_or_create_index()
        if verbose:
            print(f" [✓] Target Index: '{settings.meili_index_name}' verified")

        if reset:
            if verbose:
                print(" [*] Resetting existing documents for clean ingestion...")
            client.delete_all_documents()
            if verbose:
                print(" [✓] Existing documents cleared")

        # 2. Apply 1024D embedder and index settings
        index_settings = get_index_settings()
        if verbose:
            print(" [*] Applying 1024D Gemini embedder & schema settings...")

        task = index.update_settings(index_settings)
        client._wait_for_task(task)

        if verbose:
            print(" [✓] Index configuration applied successfully!")
            print(f"     - Target Vector Dimension: {settings.embedding_dimensions}D")
            print(f"     - Model: {settings.embedding_model}")
            print("     - Embedder Type: REST ('default')")
            print("=" * 65)

        return {
            "success": True,
            "index_name": settings.meili_index_name,
            "dimensions": settings.embedding_dimensions,
        }

    except Exception as exc:
        if verbose:
            print(f" [X] Failed to configure index: {exc}")
            print("=" * 65)
        return {"success": False, "error": str(exc)}

    finally:
        client.close()


if __name__ == "__main__":
    result = setup_meilisearch_index(reset=False, verbose=True)
    sys.exit(0 if result["success"] else 1)