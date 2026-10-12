from __future__ import annotations

import logging

from ingestion.cdc import KnowledgeBaseCDC


def configure_logging() -> None:
    """Configure logging for the CDC worker."""

    logging.basicConfig(
        level=logging.INFO,
        format=(
            "%(asctime)s | "
            "%(levelname)s | "
            "%(name)s | "
            "%(message)s"
        ),
    )


def main() -> None:
    """Start the PostgreSQL CDC worker."""

    configure_logging()

    logger = logging.getLogger(__name__)

    logger.info(
        "Starting Government Knowledge Base CDC worker..."
    )

    worker = KnowledgeBaseCDC()

    try:
        worker.run()
    finally:
        worker.search.close()


if __name__ == "__main__":
    main()