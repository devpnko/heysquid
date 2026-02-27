"""
Threads channel adapter — heysquid

Posts to Threads using the Meta Graph API.
Two-step process: create container → publish.

Required environment variables:
    THREADS_ACCESS_TOKEN, THREADS_USER_ID

Requires Meta Developer app + Instagram Business account:
    https://developers.facebook.com/docs/threads
"""

import os
import logging
import time

import requests
from dotenv import load_dotenv

from ._base import ChannelAdapter
from ..config import get_env_path

load_dotenv(get_env_path())
logger = logging.getLogger(__name__)

THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "")
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "")

GRAPH_API_BASE = "https://graph.threads.net/v1.0"


def _is_configured() -> bool:
    return bool(THREADS_ACCESS_TOKEN and THREADS_USER_ID)


class ThreadsChannel(ChannelAdapter):
    """Meta Threads API channel adapter."""

    def send_message(self, chat_id, text, **kwargs):
        """Post text to Threads.

        Two-step process:
        1. POST /{user-id}/threads → create container
        2. POST /{user-id}/threads_publish → publish

        Args:
            chat_id: Ignored (posts to own account)
            text: Post content (500 chars recommended)

        Returns:
            dict: {"ok": bool, "thread_id": str | None, "error": str | None}
        """
        if not _is_configured():
            logger.warning("Threads API not configured. Check your .env file.")
            return {"ok": False, "error": "Threads API not configured"}

        try:
            # Step 1: Create container
            create_url = f"{GRAPH_API_BASE}/{THREADS_USER_ID}/threads"
            create_resp = requests.post(
                create_url,
                params={
                    "media_type": "TEXT",
                    "text": text,
                    "access_token": THREADS_ACCESS_TOKEN,
                },
                timeout=30,
            )

            if create_resp.status_code != 200:
                error = create_resp.text[:200]
                logger.error(f"[Threads] Container creation failed ({create_resp.status_code}): {error}")
                return {"ok": False, "error": f"Container creation failed: {error}"}

            container_id = create_resp.json().get("id")
            if not container_id:
                return {"ok": False, "error": "No container ID returned"}

            # Step 2: Publish (slight delay recommended)
            time.sleep(2)

            publish_url = f"{GRAPH_API_BASE}/{THREADS_USER_ID}/threads_publish"
            publish_resp = requests.post(
                publish_url,
                params={
                    "creation_id": container_id,
                    "access_token": THREADS_ACCESS_TOKEN,
                },
                timeout=30,
            )

            if publish_resp.status_code != 200:
                error = publish_resp.text[:200]
                logger.error(f"[Threads] Publish failed ({publish_resp.status_code}): {error}")
                return {"ok": False, "error": f"Publish failed: {error}"}

            thread_id = publish_resp.json().get("id", "")
            logger.info(f"[Threads] Published: {thread_id}")
            return {"ok": True, "thread_id": thread_id}

        except Exception as e:
            logger.error(f"[Threads] Post error: {e}")
            return {"ok": False, "error": str(e)}

    def send_file(self, chat_id, file_path, **kwargs):
        """Post image/video to Threads.

        Image: requires media_type=IMAGE + image_url (public URL)
        Currently unsupported — text only.
        """
        logger.warning("[Threads] File attachments not currently supported (text only)")
        return {"ok": False, "error": "Threads file attachment not supported"}
