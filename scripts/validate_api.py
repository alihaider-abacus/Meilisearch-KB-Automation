from __future__ import annotations

import argparse
import sys

import httpx


def main() -> int:
    """Validate the running Government Knowledge Base API."""

    parser = argparse.ArgumentParser(
        description=(
            "Validate the running Government "
            "Knowledge Base API."
        )
    )

    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL of the FastAPI application.",
    )

    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    health_checks = [
        (
            "/health",
            "application health",
        ),
        (
            "/health/database",
            "database health",
        ),
        (
            "/health/search",
            "Meilisearch health",
        ),
    ]

    with httpx.Client(
        timeout=15.0
    ) as client:

        for path, description in health_checks:

            try:
                response = client.get(
                    f"{base_url}{path}"
                )

            except httpx.RequestError as exc:
                print(
                    f"{description}: request failed: {exc}"
                )
                return 1

            print(
                f"{description}: "
                f"HTTP {response.status_code}"
            )

            if response.status_code != 200:
                print(response.text)
                return 1

            try:
                data = response.json()
            except ValueError:
                print(
                    f"{description}: "
                    "response was not valid JSON."
                )
                return 1

            print(data)

    try:
        response = httpx.get(
            f"{base_url}/search",
            params={
                "q": "government",
                "mode": "keyword",
                "limit": 3,
            },
            timeout=15.0,
        )

    except httpx.RequestError as exc:
        print(
            f"keyword search: request failed: {exc}"
        )
        return 1

    print(
        "keyword search: "
        f"HTTP {response.status_code}"
    )

    if response.status_code != 200:
        print(response.text)
        return 1

    try:
        data = response.json()
    except ValueError:
        print(
            "keyword search: "
            "response was not valid JSON."
        )
        return 1

    results = data.get(
        "results",
        [],
    )

    print(
        "keyword hits returned: "
        f"{len(results)}"
    )

    for result in results:
        print(
            "- "
            f"{result.get('title') or '(untitled)'} "
            f"[{result.get('content_type')}]"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())