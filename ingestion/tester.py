"""Search Verification Module (Direct Local Meilisearch Engine).

Matches the exact localhost configuration:
  - Page-based search: Calculates exact 'totalHits' in the Knowledge Base
  - Displays Top 3 results on terminal
  - Ranking Score Threshold: 0.80 (Filters out irrelevant noise like 'Finland,zzzz')
  - Semantic Ratio: 0.70 (70% Gemini 1024D Vector, 30% Keyword)
  - Embedder: 'default' (Google Gemini gemini-embedding-001)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any, Dict, List
from config.settings import settings
from ingestion.meilisearch_client import MeilisearchClient

# Threshold calibrated to allow genuine matches while rejecting noise
RANKING_SCORE_THRESHOLD = 0.80

# 70% Gemini vector + 30% keyword (matching ui/local.js)
SEMANTIC_RATIO = 0.70


def execute_search(query: str, limit: int = 3) -> Dict[str, Any]:
    """Execute hybrid search on local Meilisearch container with accurate totalHits."""
    client = MeilisearchClient()
    try:
        index = client.client.index(settings.meili_index_name)

        # Uses page: 1 and hitsPerPage: 3 to compute the exact total matching records in the KB
        search_params: dict[str, Any] = {
            "page": 1,
            "hitsPerPage": limit,
            "showRankingScore": True,
            "rankingScoreThreshold": RANKING_SCORE_THRESHOLD,
            "hybrid": {
                "semanticRatio": SEMANTIC_RATIO,
                "embedder": "default",
            },
            "attributesToRetrieve": [
                "id", "source_id", "source_table", "content_type", "slug",
                "title", "summary", "agency_name", "published_at", "url", "form_url", "topics"
            ],
        }

        return index.search(query, search_params)
    finally:
        client.close()


def print_search_results(query: str, results: Dict[str, Any]) -> None:
    """Print the exact matching count and the Top 3 hits in PowerShell."""
    hits: List[Dict[str, Any]] = results.get("hits", [])
    total_matches = results.get("totalHits", len(hits))

    print("-" * 65)
    print(f" Query: \"{query}\"")
    print(f" Total Records Available in KB: {total_matches:,} records found")
    print(f" Showing Top {len(hits)} Results:")
    print("-" * 65)

    if not hits or total_matches == 0:
        print(" [!] No records found for this query.")
        print("-" * 65)
        return

    for rank, hit in enumerate(hits, start=1):
        score = hit.get("_rankingScore", 0.0)
        title = hit.get("title", "Untitled")
        content_type = hit.get("content_type", "unknown")
        source_table = hit.get("source_table", "unknown")
        url = hit.get("url") or "N/A"
        summary = (hit.get("summary") or "").strip()
        if summary and len(summary) > 120:
            summary = summary[:117] + "..."

        print(f" [Rank #{rank}] (Score: {score:.4f})")
        print(f"   Title:        {title}")
        print(f"   Content Type: {content_type} (Source: {source_table})")
        print(f"   URL:          {url}")
        if summary:
            print(f"   Summary:      {summary}")
        print("-" * 65)


def interactive_search_loop() -> None:
    """Interactive loop for testing queries in PowerShell."""
    print("=" * 65)
    print(" [PHASE 6] LOCAL MEILISEARCH SEARCH VERIFICATION")
    print("=" * 65)
    print(" Connected to Local Meilisearch on Port 7700 (1024D Gemini Hybrid)")
    print(" Type any query to search the Knowledge Base.")
    print(" (Press [Enter] on an empty line or type 'exit' to quit)")
    print("-" * 65)

    while True:
        try:
            query = input("\n > Enter search query: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n Exiting search.")
            break

        if not query or query.lower() in {"exit", "quit", "q"}:
            print(" [✓] Search session closed.")
            break

        results = execute_search(query, limit=3)
        print_search_results(query, results)


def run_search_tests(test_queries: List[str], verbose: bool = True) -> bool:
    """Run search against a specific list of queries."""
    if verbose:
        print("=" * 65)
        print(" [PHASE 6] LOCAL MEILISEARCH SEARCH VERIFICATION")
        print("=" * 65)

    all_passed = True
    for query in test_queries:
        try:
            results = execute_search(query, limit=3)
            if verbose:
                print_search_results(query, results)
        except Exception as exc:
            if verbose:
                print(f" [X] Search error for query '{query}': {exc}")
            all_passed = False

    if verbose:
        print("=" * 65)

    return all_passed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Local Meilisearch Knowledge Base Search")
    parser.add_argument("--query", "-q", type=str, help="Single query to test")
    args = parser.parse_args()

    if args.query:
        run_search_tests([args.query], verbose=True)
    else:
        interactive_search_loop()