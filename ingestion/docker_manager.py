"""Docker and Meilisearch Service Automation Module.

Ensures Docker Desktop is running, inspects the 'government-kb-meilisearch' container,
and automatically pulls, starts, or deploys the service if needed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Automatically ensure project root is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from typing import Any, Dict
from config.settings import settings

CONTAINER_NAME = "government-kb-meilisearch"
COMPOSE_FILE = ROOT_DIR / "docker" / "compose.yaml"
VOLUME_NAME = "docker_meilisearch_data"


def check_docker_available() -> bool:
    """Verify that Docker CLI is installed and the Docker daemon is running."""
    if not shutil.which("docker"):
        return False
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_container_status(container_name: str = CONTAINER_NAME) -> str | None:
    """Return the Docker container status (e.g., 'running', 'exited', or None if not found)."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "--format", "{{.State.Status}}", container_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def check_meili_health(url: str, timeout: float = 2.0) -> bool:
    """Perform an HTTP GET request to check the /health endpoint of Meilisearch."""
    health_url = f"{url.rstrip('/')}/health"
    try:
        req = urllib.request.Request(
            health_url,
            headers={"User-Agent": "Meilisearch-Automation-Manager"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "available"
    except Exception:
        return False
    return False


def ensure_meilisearch_service(verbose: bool = True) -> Dict[str, Any]:
    """Inspect and ensure the Meilisearch container is deployed, running, and healthy.

    Returns:
        dict with success status, container details, and health verification.
    """
    if verbose:
        print("=" * 65)
        print(" [PHASE 3] DOCKER & MEILISEARCH SERVICE AUTOMATION")
        print("=" * 65)

    # 1. Verify Docker Engine
    if not check_docker_available():
        if verbose:
            print(" [X] Docker is not running or not found in system PATH.")
            print("     Please ensure Docker Desktop is started, then re-run.")
            print("=" * 65)
        return {"success": False, "error": "Docker daemon not running"}

    if verbose:
        print(" [✓] Docker Desktop / Engine is active and responding")

    # 2. Check Container State
    status = get_container_status(CONTAINER_NAME)

    if status == "running":
        if verbose:
            print(f" [✓] Container '{CONTAINER_NAME}' is already running")
    elif status in ("exited", "created", "paused"):
        if verbose:
            print(f" [*] Container '{CONTAINER_NAME}' exists with state '{status}'. Starting it...")
        subprocess.run(["docker", "start", CONTAINER_NAME], capture_output=True, text=True)
    else:
        # Container does not exist - deploy it automatically
        if verbose:
            print(f" [*] Container '{CONTAINER_NAME}' not found.")
            print("     Automatically creating volume and deploying via docker compose...")

        # Ensure volume exists
        subprocess.run(["docker", "volume", "create", VOLUME_NAME], capture_output=True, text=True)

        # Deploy container using compose
        deploy_cmd = [
            "docker", "compose",
            "-f", str(COMPOSE_FILE),
            "up", "-d", "meilisearch",
        ]
        result = subprocess.run(deploy_cmd, capture_output=True, text=True)

        # Fallback to direct docker run if compose encounters external volume definition conflicts
        if result.returncode != 0:
            if verbose:
                print("     Notice: Running direct container deployment fallback...")
            run_cmd = [
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "-p", "7700:7700",
                "-e", "MEILI_ENV=development",
                "-e", f"MEILI_MASTER_KEY={settings.meili_master_key}",
                "-v", f"{VOLUME_NAME}:/meili_data",
                "--restart", "unless-stopped",
                "getmeili/meilisearch:latest",
            ]
            subprocess.run(run_cmd, capture_output=True, text=True)

    # 3. Health Poll Loop (up to 30 seconds)
    if verbose:
        print(f" [*] Polling Meilisearch health at {settings.meili_host}/health...")

    healthy = False
    max_wait_seconds = 30
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        if check_meili_health(settings.meili_host):
            healthy = True
            break
        time.sleep(1)

    if not healthy:
        if verbose:
            print(f" [X] Meilisearch failed to become healthy within {max_wait_seconds} seconds.")
            print(f"     Check logs with: docker logs {CONTAINER_NAME}")
            print("=" * 65)
        return {"success": False, "error": "Health check timeout"}

    if verbose:
        print(f" [✓] Health check verified: {settings.meili_host}/health")
        print("     Status: 'available' (Ready for index configuration & ingestion)")
        print("=" * 65)

    return {
        "success": True,
        "container": CONTAINER_NAME,
        "host": settings.meili_host,
        "status": "available",
    }


if __name__ == "__main__":
    result = ensure_meilisearch_service(verbose=True)
    sys.exit(0 if result["success"] else 1)