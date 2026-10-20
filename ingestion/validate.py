from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    """Result of document validation."""

    valid: bool
    errors: tuple[str, ...]


def validate_document(
    document: dict[str, Any],
) -> ValidationResult:
    """Validate one transformed Meilisearch document."""

    errors: list[str] = []

    # 1. Identity
    document_id = document.get("id")
    if not isinstance(document_id, str) or not document_id.strip():
        errors.append("Missing document id")

    # 2. Searchable content
    title = document.get("title")
    if not isinstance(title, str) or not title.strip():
        errors.append("Missing title")

    search_text = document.get("search_text")
    if not isinstance(search_text, str) or not search_text.strip():
        errors.append("Missing search_text")

    # 3. Topics collection
    topics = document.get("topics")
    if not isinstance(topics, list):
        errors.append("topics must be a list")

    return ValidationResult(
        valid=not errors,
        errors=tuple(errors),
    )


def validate_documents(
    documents: list[dict[str, Any]],
) -> None:
    """Validate a batch of transformed documents."""

    failures: list[str] = []

    for document in documents:
        result = validate_document(document)
        if not result.valid:
            failures.append(
                f"{document.get('id', '<unknown>')}: "
                + "; ".join(result.errors)
            )

    if failures:
        message = "\n".join(failures[:20])
        if len(failures) > 20:
            message += f"\n...and {len(failures) - 20} more failures."
        raise ValueError("Document validation failed:\n" + message)