"""Master Orchestrator CLI for Government Knowledge Base Automation.

Automates the complete workflow:
  1. Environment & Secret Verification
  2. Umbrella Database & Table Inspection
  3. Docker Meilisearch Service Management & Auto-Deployment
  4. Meilisearch 1024D Embedder & Index Schema Configuration
  5. Knowledge Base Data Ingestion Pipeline (Silent Legacy Vector Exclusion)
  6. Interactive Search Verification (User Enters Custom Queries in Terminal)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from ingestion.env_checker import verify_environment
from ingestion.db_inspector import inspect_database
from ingestion.docker_manager import ensure_meilisearch_service
from ingestion.index_setup import setup_meilisearch_index
from ingestion.data_pipeline import run_pipeline
from ingestion.meilisearch_client import MeilisearchClient
from ingestion.tester import interactive_search_loop, run_search_tests


def print_banner() -> None:
    """Print the master startup banner."""
    print()
    print("=" * 65)
    print(" GOVERNMENT OF BERMUDA - AUTOMATED MEILISEARCH PIPELINE")
    print("=" * 65)
    print(f" Project ID:          {settings.project_id}")
    print(f" Instance Name:       {settings.instance_name}")
    print(f" Umbrella Database:   {settings.db_name}")
    print(f" Embedding Model:     {settings.embedding_model} ({settings.embedding_dimensions}D)")
    print(f" Target Host:         {settings.meili_host}")
    print(f" Target Index:        {settings.meili_index_name}")
    print("=" * 65)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Master Ingestion Orchestrator")
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="Skip re-ingesting data if documents are already indexed in Meilisearch",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Batch size for Meilisearch ingestion (default: 200)",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Run a single non-interactive search query instead of interactive prompt",
    )
    args = parser.parse_args()

    print_banner()
    start_total_time = time.time()

    # ------------------------------------------------------------------
    # PHASE 1: Environment & Settings Check
    # ------------------------------------------------------------------
    is_env_valid, _ = verify_environment(verbose=True)
    if not is_env_valid:
        print("\n [!] Orchestrator stopped at Phase 1: Environment Check Failed.\n")
        return 1
    print()

    # ------------------------------------------------------------------
    # PHASE 2: Database Inspection & Silent Extraction
    # ------------------------------------------------------------------
    db_info = inspect_database(verbose=True)
    if not db_info.get("connected"):
        print("\n [!] Orchestrator stopped at Phase 2: Database Connection Failed.\n")
        return 1
    print()

    # ------------------------------------------------------------------
    # PHASE 3: Docker & Meilisearch Auto-Deploy
    # ------------------------------------------------------------------
    docker_info = ensure_meilisearch_service(verbose=True)
    if not docker_info.get("success"):
        print("\n [!] Orchestrator stopped at Phase 3: Meilisearch Service Failed.\n")
        return 1
    print()

    # ------------------------------------------------------------------
    # PHASE 4: Meilisearch 1024D Embedder Configuration
    # ------------------------------------------------------------------
    index_info = setup_meilisearch_index(reset=False, verbose=True)
    if not index_info.get("success"):
        print("\n [!] Orchestrator stopped at Phase 4: Index Configuration Failed.\n")
        return 1
    print()

    # ------------------------------------------------------------------
    # PHASE 5: Data Pipeline Ingestion
    # ------------------------------------------------------------------
    client = MeilisearchClient()
    current_doc_count = client.document_count()
    client.close()

    if args.skip_ingest and current_doc_count > 0:
        print("=" * 65)
        print(" [PHASE 5] DATA INGESTION (SKIPPED VIA --skip-ingest FLAG)")
        print("=" * 65)
        print(f" [✓] Existing index contains {current_doc_count:,} documents.")
        print("     Skipping re-ingestion and proceeding directly to interactive search.")
        print("=" * 65)
    else:
        pipeline_info = run_pipeline(
            batch_size=args.batch_size,
            clear_existing=True,
            verbose=True,
        )
        if not pipeline_info.get("success"):
            print("\n [!] Orchestrator stopped at Phase 5: Ingestion Pipeline Failed.\n")
            return 1
    print()

    # ------------------------------------------------------------------
    # PHASE 6: Interactive Search Verification (User inputs queries)
    # ------------------------------------------------------------------
    if args.query:
        # Non-interactive mode if query was passed as a command-line flag
        run_search_tests([args.query], verbose=True)
    else:
        # Interactive mode: prompt user directly in PowerShell!
        interactive_search_loop()
    print()

    total_time = time.time() - start_total_time
    print("=" * 65)
    print(" [✓] MASTER ORCHESTRATION COMPLETED SUCCESSFULLY!")
    print(f"     Total Workflow Duration: {total_time:.2f} seconds")
    print("=" * 65)
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())