from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration and environment settings."""

    # ------------------------------------------------------------------
    # Application & Project Metadata
    # ------------------------------------------------------------------

    app_name: str = "Government of Bermuda"
    app_env: str = "development"
    log_level: str = "INFO"

    project_id: str = "prj-gob-ss-oss-portal-d"
    instance_name: str = "chatbot-gob-instance-dev"

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

    cdc_slot_name: str = "government_kb_slot"
    cdc_plugin: str = "wal2json"

    # ------------------------------------------------------------------
    # Meilisearch
    # ------------------------------------------------------------------

    meili_host: str = "http://localhost:7700"
    meili_master_key: str = ""
    meili_search_key: str = ""
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
    kb_excluded_tables: str = ""

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    embedding_model: str = "gemini-embedding-001"

    embedding_dimensions: int = Field(
        default=1024,
        ge=1,
        description="Target vector dimension. Switched to 1024D for autonomous Meilisearch vectorization.",
    )

    gemini_api_key: str = ""

    pinecone_api_key: str = ""
    pinecone_index_name: str = "bermuda-kb"
    pinecone_host: str = ""

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