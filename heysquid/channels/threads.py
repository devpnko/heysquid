"""
Threads 채널 어댑터 — heysquid

Meta Graph API를 사용하여 Threads에 게시합니다.
2단계: 컨테이너 생성 → 게시(publish).

필요 환경변수:
    THREADS_ACCESS_TOKEN, THREADS_USER_ID

Meta Developer 앱 + Instagram Business 계정 필요:
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
    """Meta Threads API 채널 어댑터."""

    def send_message(self, chat_id, text, **kwargs):
        """Threads에 텍스트 게시.

        2단계 프로세스:
        1. POST /{user-id}/threads → 컨테이너 생성
        2. POST /{user-id}/threads_publish → 게시

        Args:
            chat_id: 무시됨 (자기 계정에 게시)
            text: 게시 내용 (500자 권장)

        Returns:
            dict: {"ok": bool, "thread_id": str | None, "error": str | None}
        """
        if not _is_configured():
            logger.warning("Threads API 미설정. .env 파일을 확인하세요.")
            return {"ok": False, "error": "Threads API 미설정"}

        try:
            # Step 1: 컨테이너 생성
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
                logger.error(f"[Threads] 컨테이너 생성 실패 ({create_resp.status_code}): {error}")
                return {"ok": False, "error": f"컨테이너 생성 실패: {error}"}

            container_id = create_resp.json().get("id")
            if not container_id:
                return {"ok": False, "error": "컨테이너 ID 없음"}

            # Step 2: 게시 (약간의 딜레이 권장)
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
                logger.error(f"[Threads] 게시 실패 ({publish_resp.status_code}): {error}")
                return {"ok": False, "error": f"게시 실패: {error}"}

            thread_id = publish_resp.json().get("id", "")
            logger.info(f"[Threads] 게시 완료: {thread_id}")
            return {"ok": True, "thread_id": thread_id}

        except Exception as e:
            logger.error(f"[Threads] 게시 오류: {e}")
            return {"ok": False, "error": str(e)}

    def send_file(self, chat_id, file_path, **kwargs):
        """Threads 이미지/동영상 게시.

        이미지: media_type=IMAGE + image_url 필요 (공개 URL)
        현재는 미지원 — 텍스트 전용.
        """
        logger.warning("[Threads] 파일 첨부는 현재 미지원 (텍스트 전용)")
        return {"ok": False, "error": "Threads 파일 첨부 미지원"}
