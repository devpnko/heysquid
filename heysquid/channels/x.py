"""
X (Twitter) 채널 어댑터 — heysquid

X API v2를 사용하여 트윗을 게시합니다.
무료 티어: write-only (포스팅만 가능).

필요 환경변수:
    X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET

X Developer Portal에서 앱 생성 후 키 발급 필요:
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
    """OAuth 1.0a 인증 헤더 생성."""
    oauth_params = {
        "oauth_consumer_key": X_API_KEY,
        "oauth_nonce": hashlib.md5(str(time.time()).encode()).hexdigest(),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": X_ACCESS_TOKEN,
        "oauth_version": "1.0",
    }

    # 서명 베이스 문자열
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
    """X (Twitter) API v2 채널 어댑터."""

    def send_message(self, chat_id, text, **kwargs):
        """트윗 게시.

        Args:
            chat_id: 무시됨 (X는 자기 계정에 게시)
            text: 트윗 내용 (280자 제한)

        Returns:
            dict: {"ok": bool, "tweet_id": str | None, "error": str | None}
        """
        if not _is_configured():
            logger.warning("X API 키 미설정. .env 파일을 확인하세요.")
            return {"ok": False, "error": "X API 키 미설정"}

        # 280자 제한
        if len(text) > 280:
            logger.warning(f"트윗 길이 초과: {len(text)}자 → 280자로 잘림")
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
                logger.info(f"[X] 트윗 게시 완료: {tweet_id}")
                return {"ok": True, "tweet_id": tweet_id}
            else:
                error = resp.text[:200]
                logger.error(f"[X] 트윗 실패 ({resp.status_code}): {error}")
                return {"ok": False, "error": f"{resp.status_code}: {error}"}

        except Exception as e:
            logger.error(f"[X] 트윗 게시 오류: {e}")
            return {"ok": False, "error": str(e)}

    def send_file(self, chat_id, file_path, **kwargs):
        """X 미디어 업로드는 별도 API 필요 (v1.1 media/upload).

        현재는 미지원 — 텍스트 전용.
        """
        logger.warning("[X] 파일 첨부는 현재 미지원 (텍스트 전용)")
        return {"ok": False, "error": "X 파일 첨부 미지원"}
