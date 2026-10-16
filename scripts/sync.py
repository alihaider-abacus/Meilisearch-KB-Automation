from __future__ import annotations

import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import argparse

from ingestion.sync import KnowledgeBaseSync


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Synchronize the Government Knowledge Base "
            "into Meilisearch."
        )
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete existing Meilisearch documents before syncing.",
    )

    args = parser.parse_args()

    sync = KnowledgeBaseSync()

    counts = sync.run(
        clear_existing=args.clear,
    )

    print()
    print("Synchronization complete.")
    print()

    total = 0

    for table_name, count in sorted(counts.items()):
        print(f"{table_name}: {count}")
        total += count

    print(f"TOTAL: {total}")


if __name__ == "__main__":
    main()