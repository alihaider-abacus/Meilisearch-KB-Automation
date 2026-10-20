from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any
from config.settings import settings


def get_index_settings() -> dict[str, Any]:
    """Build fresh Meilisearch index configuration with 1024D Gemini embedder."""
    return {
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
                "documentTemplate": "{{doc.search_text | default: doc.title}}",
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
                            },
                            "outputDimensionality": settings.embedding_dimensions,
                        }
                    ]
                },
                "response": {
                    "embeddings": [{"values": "{{embedding}}"}]
                },
            },
        },
    }


INDEX_SETTINGS: dict[str, Any] = get_index_settings()