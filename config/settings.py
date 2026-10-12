from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration."""

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    app_name: str = "Government of Bermuda"
    app_env: str = "development"
    log_level: str = "INFO"

    # ------------------------------------------------------------------
    # PostgreSQL
    # ------------------------------------------------------------------

    db_host: str = "localhost"

    db_port: int = Field(
        default=5432,
        ge=1,
        le=65535,
    )

    db_name: str = "API-Data"
    db_user: str = ""
    db_password: str = ""

    # ------------------------------------------------------------------
    # Meilisearch
    # ------------------------------------------------------------------

    meili_host: str = "http://localhost:7700"
    meili_master_key: str = ""
    meili_index_name: str = "government_content"

    meili_timeout_seconds: float = Field(
    default=30.0,
    gt=0,
)



    # ------------------------------------------------------------------
    # Knowledge Base
    # ------------------------------------------------------------------

    kb_schema: str = "public"
    kb_table_suffix: str = "_kb"

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    embedding_model: str = "gemini-embedding-001"

    embedding_dimensions: int = Field(
        default=3072,
        ge=1,
    )

    gemini_api_key: str = ""
    # ------------------------------------------------------------------
    # Vertex AI
    # ------------------------------------------------------------------

    vertex_ai_project: str = ""
    vertex_ai_location: str = "us-central1"

    search_embedding_task_type: str = "RETRIEVAL_QUERY"

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    # The application exposes only one search strategy:
    #
    #   70% semantic
    #   30% keyword
    #
    # Meilisearch's semanticRatio is the semantic portion.

    search_hybrid_semantic_ratio: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
    )

    # UI/API page size.
    search_default_limit: int = Field(
        default=20,
        ge=1,
        le=20,
    )

    search_max_limit: int = Field(
        default=20,
        ge=1,
        le=20,
    )

    # Minimum semantic relevance accepted for a result.
    #
    # This prevents completely unrelated queries from returning
    # arbitrary semantic matches.

    search_min_semantic_score: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
    )

    # Maximum number of autocomplete suggestions.

    search_suggestion_limit: int = Field(
        default=5,
        ge=1,
        le=5,
    )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    ingestion_batch_size: int = Field(
        default=100,
        ge=1,
    )

    ingestion_max_retries: int = Field(
        default=3,
        ge=0,
    )

    read_only_source: bool = True

    # ------------------------------------------------------------------
    # Configuration
    # ------------------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8-sig",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def excluded_kb_tables(self) -> set[str]:
        """Return normalized excluded table names."""

        return {
            table.strip()
            for table in self.kb_excluded_tables.split(",")
            if table.strip()
        }


settings = Settings()