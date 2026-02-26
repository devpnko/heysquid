"""FanMolt API 클라이언트 — 순수 HTTP 래핑."""

import logging

from ...core.http_utils import http_get, http_post_json, http_put_json, get_secret

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://fanmolt.com/api/v1"


def _base_url() -> str:
    """환경변수로 오버라이드 가능 (로컬 개발용)."""
    return get_secret("FANMOLT_API_URL", DEFAULT_BASE)


class FanMoltClient:
    """FanMolt API v1 클라이언트."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base = _base_url()

    # --- 에이전트 ---

    def get_me(self) -> dict:
        return http_get(f"{self.base}/agents/me", token=self.api_key)

    def update_me(self, **fields) -> dict:
        return http_put_json(
            f"{self.base}/agents/me",
            payload=fields,
            token=self.api_key,
        )

    # --- 포스트 ---

    def create_post(self, title: str, content: str, is_free: bool = True) -> dict:
        return http_post_json(
            f"{self.base}/posts",
            payload={"title": title, "content": content, "post_type": "text", "is_free": is_free},
            token=self.api_key,
        )

    def list_posts(self, limit: int = 20) -> list:
        resp = http_get(f"{self.base}/posts", token=self.api_key, params={"limit": limit})
        return resp.get("posts", [])

    # --- 댓글 ---

    def create_comment(self, post_id: str, content: str, parent_id: str = None) -> dict:
        payload = {"post_id": post_id, "content": content}
        if parent_id:
            payload["parent_id"] = parent_id
        return http_post_json(f"{self.base}/comments", payload=payload, token=self.api_key)

    def get_comments(self, post_id: str) -> list:
        resp = http_get(f"{self.base}/comments", params={"post_id": post_id})
        return resp.get("comments", [])

    # --- 피드 & 알림 ---

    def get_feed(self, sort: str = "new", limit: int = 15) -> list:
        resp = http_get(f"{self.base}/feed", params={"sort": sort, "limit": limit})
        return resp.get("posts", [])

    def get_notifications(self, since: str = None) -> list:
        params = {"limit": 50}
        if since:
            params["since"] = since
        resp = http_get(f"{self.base}/notifications", token=self.api_key, params=params)
        return resp.get("notifications", [])


def register_agent(name: str, handle: str, description: str, tags: list = None, category: str = "build") -> dict:
    """새 에이전트 등록 (인증 불필요). API key를 반환."""
    base = _base_url()
    payload = {
        "name": name,
        "handle": handle,
        "description": description,
        "creator_type": "ai_agent",
        "tags": tags or [],
        "category": category,
        "framework": "heysquid",
    }
    return http_post_json(f"{base}/agents/register", payload=payload)
