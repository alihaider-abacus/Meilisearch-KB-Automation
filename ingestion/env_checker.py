"""Environment and Configuration Checker Module.

Validates that all required secrets, database credentials, project metadata,
and embedding dimensions are properly set before starting the pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Automatically ensure project root is in sys.path so 'config' is always found
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Tuple
from config.settings import settings


def mask_secret(value: str) -> str:
    """Mask a secret value for safe terminal printing."""
    if not value:
        return "[MISSING]"
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def verify_environment(verbose: bool = True) -> Tuple[bool, list[str]]:
    """Inspect and validate all critical environment configuration values.

    Returns:
        (is_valid, list_of_errors)
    """
    errors: list[str] = []

    if verbose:
        print("=" * 65)
        print(" [PHASE 1] ENVIRONMENT & CONFIGURATION CHECK")
        print("=" * 65)

    # 1. Project & Instance Metadata
    if not settings.project_id:
        errors.append("PROJECT_ID is not configured in .env")
    elif verbose:
        print(f" [OK] Project ID:         {settings.project_id}")

    if not settings.instance_name:
        errors.append("INSTANCE_NAME is not configured in .env")
    elif verbose:
        print(f" [OK] Instance Name:      {settings.instance_name}")

    # 2. Database Configuration
    if settings.db_name != "API-Data":
        errors.append(f"DB_NAME must be 'API-Data' (found: {settings.db_name})")
    elif verbose:
        print(f" [OK] Umbrella Database:  {settings.db_name}")

    if not settings.db_user or not settings.db_password:
        errors.append("DB_USER or DB_PASSWORD is missing in .env")
    elif verbose:
        print(f" [OK] DB User:            {settings.db_user} (password: {mask_secret(settings.db_password)})")
        print(f" [OK] DB Target Host:     {settings.db_host}:{settings.db_port}")

    # 3. Meilisearch Configuration
    if not settings.meili_master_key:
        errors.append("MEILI_MASTER_KEY is not configured in .env")
    elif verbose:
        print(f" [OK] Meilisearch Host:   {settings.meili_host}")
        print(f" [OK] Meili Master Key:   {mask_secret(settings.meili_master_key)}")
        print(f" [OK] Target Index:       {settings.meili_index_name}")

    # 4. Gemini Embedder Configuration
    if not settings.gemini_api_key:
        errors.append("GEMINI_API_KEY is missing in .env")
    elif verbose:
        print(f" [OK] Gemini API Key:     {mask_secret(settings.gemini_api_key)}")

    # 5. Embeddings Dimension Verification
    if settings.embedding_dimensions != 1024:
        errors.append(
            f"EMBEDDING_DIMENSIONS must be 1024 for Meilisearch vectorization (found: {settings.embedding_dimensions})"
        )
    elif verbose:
        print(f" [OK] Embedding Dimension:{settings.embedding_dimensions}D (Model: {settings.embedding_model})")

    if verbose:
        print("-" * 65)

    if errors:
        if verbose:
            print(" [X] ENVIRONMENT VERIFICATION FAILED:")
            for err in errors:
                print(f"     - {err}")
            print("=" * 65)
        return False, errors

    if verbose:
        print(" [✓] ALL ENVIRONMENT VARIABLES & METADATA VERIFIED SUCCESSFULLY")
        print("=" * 65)

    return True, []


if __name__ == "__main__":
    is_valid, _ = verify_environment(verbose=True)
    sys.exit(0 if is_valid else 1)