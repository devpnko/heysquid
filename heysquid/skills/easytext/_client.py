"""EasyText API client — thread generation + trends."""

import re

from ...core.http_utils import http_get, http_post_json

BASE_URL = "https://easytext.store/api"

VERSION_SEP = re.compile(r"===VER\d+===")


def generate_thread(
    topic: str,
    content_type: str = "opinion",
    format: str = "three",
) -> str:
    """Generate thread drafts via EasyText API.

    Args:
        topic: Subject to write about.
        content_type: opinion | promotion | info | daily
        format: three | five | free

    Returns:
        Raw result text string.
    """
    resp = http_post_json(
        f"{BASE_URL}/threads/generate",
        payload={
            "content": topic,
            "contentType": content_type,
            "format": format,
        },
    )
    return resp.get("result", "")


def parse_versions(result_text: str) -> list[str]:
    """Split raw result into individual versions.

    The API separates versions with ===VER1===, ===VER2===, etc.
    Returns a list of stripped version strings.
    """
    parts = VERSION_SEP.split(result_text)
    return [p.strip() for p in parts if p.strip()]


def get_google_trends() -> dict:
    """Fetch real-time Google Trends from EasyText."""
    return http_get(f"{BASE_URL}/trends")


def get_og_meta(threads_url: str) -> dict:
    """Fetch OG metadata for a Threads URL."""
    return http_get(f"{BASE_URL}/threads/og", params={"url": threads_url})
