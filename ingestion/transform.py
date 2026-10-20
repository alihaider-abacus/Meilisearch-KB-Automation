from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup


SUPPORTED_TABLES = {
    "articles_kb",
    "news_kb",
    "pages_kb",
    "services_kb",
}


def html_to_text(
    value: str | None,
) -> str:
    """Convert HTML into normalized plain text."""

    if not value:
        return ""

    soup = BeautifulSoup(
        value,
        "html.parser",
    )

    text = soup.get_text(
        " ",
        strip=True,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def clean_text(
    value: Any,
) -> str:
    """Normalize a value into plain text."""

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
    ).strip()


def normalize_topics(
    value: Any,
) -> list[str]:
    """Normalize topics into a list of strings."""

    if value is None:
        return []

    if isinstance(
        value,
        list,
    ):
        return [
            clean_text(item)
            for item in value
            if clean_text(item)
        ]

    if isinstance(
        value,
        tuple,
    ):
        return [
            clean_text(item)
            for item in value
            if clean_text(item)
        ]

    cleaned = clean_text(value)

    return [cleaned] if cleaned else []


def build_search_text(
    *,
    title: str,
    summary: str = "",
    content: str = "",
    agency_name: str = "",
    topics: list[str] | None = None,
) -> str:
    """Build consolidated keyword-search text."""

    parts: list[str] = [
        clean_text(title),
        clean_text(summary),
        clean_text(content),
        clean_text(agency_name),
    ]

    if topics:
        parts.append(
            clean_text(
                " ".join(topics)
            )
        )

    return "\n\n".join(
        part
        for part in parts
        if part
    )


def transform_record(
    source_table: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Transform a PostgreSQL source row into a Meilisearch document."""

    if source_table not in SUPPORTED_TABLES:
        raise ValueError(
            f"Unsupported source table: {source_table!r}"
        )

    title = clean_text(row.get("title"))
    agency_name = clean_text(row.get("agency_name"))
    topics = normalize_topics(row.get("topics"))

    if source_table in {"articles_kb", "news_kb"}:
        summary = clean_text(row.get("summary"))
        content = html_to_text(row.get("body_html"))
    elif source_table == "pages_kb":
        summary = ""
        content = clean_text(row.get("content"))
    else:
        summary = clean_text(row.get("description"))
        content = html_to_text(row.get("body_html"))

    record_id = str(row["id"])

    # Document ready for Meilisearch autonomous 1024D vectorization
    document = {
        "id": f"{source_table}:{record_id}",
        "source_id": record_id,
        "source_table": source_table,
        "content_type": source_table.removesuffix("_kb"),
        "slug": clean_text(row.get("slug")) or None,
        "title": title,
        "summary": summary,
        "content": content,
        "agency_name": agency_name or None,
        "published_at": (
            row["published_at"].isoformat()
            if row.get("published_at")
            else None
        ),
        "url": row.get("url"),
        "form_url": row.get("form_url"),
        "topics": topics,
        "search_text": build_search_text(
            title=title,
            summary=summary,
            content=content,
            agency_name=agency_name,
            topics=topics,
        ),
    }

    return document