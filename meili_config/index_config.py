from __future__ import annotations

from typing import Any

from config.settings import settings


INDEX_SETTINGS: dict[str, Any] = {
    "searchableAttributes": [
        "title",
        "summary",
        "content",
        "agency_name",
        "topics",
        "search_text",
    ],

    "filterableAttributes": [
        "content_type",
        "source_table",
        "agency_name",
        "topics",
        "published_at",
    ],

    "sortableAttributes": [
        "published_at",
    ],

    "displayedAttributes": [
        "id",
        "source_id",
        "source_table",
        "content_type",
        "slug",
        "title",
        "summary",
        "content",
        "agency_name",
        "published_at",
        "url",
        "form_url",
        "topics",
    ],

    "typoTolerance": {
        "enabled": True,
    },

    "pagination": {
        "maxTotalHits": 10000,
    },

    "embedders": {
        "default": {
            "source": "rest",
            "dimensions": settings.embedding_dimensions,
            "url": "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents",
            "documentTemplate": (
                "{{title}} {{summary}} "
                "{{content}} {{agency_name}} "
                "{{topics}}"
            ),
            "headers": {
                "Content-Type": "application/json",
                "x-goog-api-key": settings.gemini_api_key,
            },
            "request": {
                "requests": [
                    {
                        "model": f"models/{settings.embedding_model}",
                        "content": {
                            "parts": [{"text": "{{text}}"}]
                        }
                    }
                ]
            },
            "response": {
                "embeddings": [{"values": "{{embedding}}"}]
            }
        },
    },
}