from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from config.settings import settings


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

    # --------------------------------------------------------------
    # Identity
    # --------------------------------------------------------------

    document_id = document.get("id")

    if not isinstance(document_id, str) or not document_id.strip():
        errors.append("Missing document id")

    # --------------------------------------------------------------
    # Searchable content
    # --------------------------------------------------------------

    title = document.get("title")

    if not isinstance(title, str) or not title.strip():
        errors.append("Missing title")

    search_text = document.get("search_text")

    if not isinstance(search_text, str) or not search_text.strip():
        errors.append("Missing search_text")

    # --------------------------------------------------------------
    # Embedding
    # --------------------------------------------------------------

    embedding_container = document.get(
        "_vectors"
    )

    if not isinstance(
        embedding_container,
        dict,
    ):
        errors.append(
            "Missing _vectors object"
        )

    else:
        embedding = embedding_container.get(
            "default"
        )

        if not isinstance(
            embedding,
            list,
        ):
            errors.append(
                "Missing default embedding"
            )

        else:
            if len(embedding) != settings.embedding_dimensions:
                errors.append(
                    "Invalid embedding dimensions: "
                    f"expected "
                    f"{settings.embedding_dimensions}, "
                    f"got {len(embedding)}"
                )

            for index, value in enumerate(embedding):
                if not isinstance(
                    value,
                    (int, float),
                ):
                    errors.append(
                        "Embedding contains "
                        f"a non-numeric value at index {index}"
                    )
                    break

                if not math.isfinite(float(value)):
                    errors.append(
                        "Embedding contains "
                        f"a non-finite value at index {index}"
                    )
                    break

    # --------------------------------------------------------------
    # Basic collection fields
    # --------------------------------------------------------------

    topics = document.get("topics")

    if not isinstance(topics, list):
        errors.append(
            "topics must be a list"
        )

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
        result = validate_document(
            document
        )

        if not result.valid:
            failures.append(
                f"{document.get('id', '<unknown>')}: "
                + "; ".join(result.errors)
            )

    if failures:
        message = "\n".join(
            failures[:20]
        )

        if len(failures) > 20:
            message += (
                "\n..."
                f"and {len(failures) - 20} "
                "more failures."
            )

        raise ValueError(
            "Document validation failed:\n"
            + message
        )