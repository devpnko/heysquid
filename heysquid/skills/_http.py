"""HTTP 유틸리티 — 외부 API 스킬용 공용 헬퍼."""

import os
import logging

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


def get_secret(key: str, default: str = "") -> str:
    """환경변수에서 시크릿 로드. .env 자동 로드."""
    from dotenv import load_dotenv
    from heysquid.core.config import get_env_path

    load_dotenv(get_env_path())
    return os.getenv(key, default)


def http_get(
    url: str,
    token: str = None,
    params: dict = None,
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """GET 요청. JSON 응답 반환."""
    h = headers.copy() if headers else {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=h, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


def http_post_json(
    url: str,
    payload: dict,
    token: str = None,
    auth_scheme: str = "Bearer",
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST JSON 요청."""
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"{auth_scheme} {token}"
    if headers:
        h.update(headers)
    r = requests.post(url, json=payload, headers=h, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text, "status_code": r.status_code}


def http_post_form(
    url: str,
    data: dict,
    token: str = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST form-encoded 요청 (Buffer 등 레거시 API용)."""
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.post(url, data=data, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()
