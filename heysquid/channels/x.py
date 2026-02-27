"""
X (Twitter) channel adapter — heysquid

Posts tweets using the X API v2.
Free tier: write-only (posting only).

Required environment variables:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET

Create an app and get keys from the X Developer Portal:
    https://developer.x.com/en/portal/dashboard
"""

import os
import logging
import hashlib
import hmac
import time
import urllib.parse

import requests
from dotenv import load_dotenv

from ._base import ChannelAdapter
from ..config import get_env_path

load_dotenv(get_env_path())
logger = logging.getLogger(__name__)

X_API_KEY = os.getenv("X_API_KEY", "")
X_API_SECRET = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "")

TWEET_URL = "https://api.x.com/2/tweets"


def _is_configured() -> bool:
    return all([X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET])


def _oauth1_header(method: str, url: str, body_params: dict | None = None) -> str:
    """Generate OAuth 1.0a authorization header."""
    oauth_params = {
        "oauth_consumer_key": X_API_KEY,
        "oauth_nonce": hashlib.md5(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": X_ACCESS_TOKEN,
        "oauth_version": "1.0",
    }

    # Signature base string
    all_params = {**oauth_params}
    if body_params:
        all_params.update(body_params)

    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
        for k, v in sorted(all_params.items())
    )
    base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(sorted_params, safe='')}"

    signing_key = f"{urllib.parse.quote(X_API_SECRET, safe='')}&{urllib.parse.quote(X_ACCESS_SECRET, safe='')}"

    import base64
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()

    oauth_params["oauth_signature"] = signature

    header_parts = ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_parts}"


class XChannel(ChannelAdapter):
    """X (Twitter) API v2 channel adapter."""

    def send_message(self, chat_id, text, **kwargs):
        """Post a tweet.

        Args:
            chat_id: Ignored (X posts to own account)
            text: Tweet content (280 char limit)

        Returns:
            dict: {"ok": bool, "tweet_id": str | None, "error": str | None}
        """
        if not _is_configured():
            logger.warning("X API keys not configured. Check your .env file.")
            return {"ok": False, "error": "X API keys not configured"}

        # 280 char limit
        if len(text) > 280:
            logger.warning(f"Tweet length exceeded: {len(text)} chars → truncated to 280")
            text = text[:277] + "..."

        try:
            payload = {"text": text}

            auth_header = _oauth1_header("POST", TWEET_URL)

            resp = requests.post(
                TWEET_URL,
                json=payload,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
                timeout=30,
            )

            if resp.status_code in (200, 201):
                data = resp.json().get("data", {})
                tweet_id = data.get("id", "")
                logger.info(f"[X] Tweet posted: {tweet_id}")
                return {"ok": True, "tweet_id": tweet_id}
            else:
                error = resp.text[:200]
                logger.error(f"[X] Tweet failed ({resp.status_code}): {error}")
                return {"ok": False, "error": f"{resp.status_code}: {error}"}

        except Exception as e:
            logger.error(f"[X] Tweet post error: {e}")
            return {"ok": False, "error": str(e)}

    def send_file(self, chat_id, file_path, **kwargs):
        """X media upload requires a separate API (v1.1 media/upload).

        Currently unsupported — text only.
        """
        logger.warning("[X] File attachments not currently supported (text only)")
        return {"ok": False, "error": "X file attachment not supported"}
