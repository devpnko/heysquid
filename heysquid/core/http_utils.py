"""HTTP 유틸리티 — 외부 API 플러그인용 공용 헬퍼."""

import os
import logging

import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30


def _is_retryable(exc: BaseException) -> bool:
    """재시도 대상 예외 판별 (네트워크 + 5xx + 429)."""
    if isinstance(exc, requests.ConnectionError | requests.Timeout):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return False


_retry_policy = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)


def get_secret(key: str, default: str = "") -> str:
    """환경변수에서 시크릿 로드. .env 자동 로드."""
    from dotenv import load_dotenv
    from heysquid.core.config import get_env_path

    load_dotenv(get_env_path())
    return os.getenv(key, default)


@_retry_policy
def http_get_text(
    url: str,
    token: str = None,
    params: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> str:
    """GET 요청. 텍스트(마크다운 등) 응답 반환. (3회 재시도, exponential backoff)"""
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=h, params=params, timeout=timeout)
    r.raise_for_status()
    return r.text


@_retry_policy
def http_get(
    url: str,
    token: str = None,
    params: dict = None,
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """GET 요청. JSON 응답 반환. (3회 재시도, exponential backoff)"""
    h = headers.copy() if headers else {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.get(url, headers=h, params=params, timeout=timeout)
    r.raise_for_status()
    return r.json()


@_retry_policy
def http_post_json(
    url: str,
    payload: dict,
    token: str = None,
    auth_scheme: str = "Bearer",
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST JSON 요청. (3회 재시도, exponential backoff)"""
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


@_retry_policy
def http_put_json(
    url: str,
    payload: dict,
    token: str = None,
    headers: dict = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """PUT JSON 요청. (3회 재시도, exponential backoff)"""
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    if headers:
        h.update(headers)
    r = requests.put(url, json=payload, headers=h, timeout=timeout)
    r.raise_for_status()
    try:
        return r.json()
    except Exception:
        return {"raw": r.text, "status_code": r.status_code}


@_retry_policy
def http_post_form(
    url: str,
    data: dict,
    token: str = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """POST form-encoded 요청 (Buffer 등 레거시 API용). (3회 재시도)"""
    h = {}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = requests.post(url, data=data, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()
