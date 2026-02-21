"""
heysquid.channels.discord_channel — Discord sender (REST API 기반).

⚠️ 파일명 주의: discord.py가 아닌 discord_channel.py (D4 — 라이브러리 이름 충돌 방지)

역할:
- PM 응답 및 브로드캐스트 메시지를 Discord로 전송
- 2000자 제한 자동 분할 (D1)
- 파일 업로드 (25MB 제한, D2)
- Gateway 연결 없이 REST API만 사용 (sender는 HTTP로 충분)

사용법:
    from heysquid.channels.discord_channel import send_message_sync, send_files_sync
"""

import os
import time

import requests
from dotenv import load_dotenv

from ..config import get_env_path

load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
API_BASE = "https://discord.com/api/v10"

# 세션 재사용
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "Authorization": f"Bot {BOT_TOKEN}",
        })
    return _session


def _send_chunk(channel_id, text):
    """단일 메시지 전송 (REST API)"""
    session = _get_session()
    resp = session.post(
        f"{API_BASE}/channels/{channel_id}/messages",
        json={"content": text},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    return True


def send_message_sync(channel_id, text, _save=True, **kwargs):
    """Discord 메시지 전송 (동기).

    Args:
        channel_id: Discord 채널 ID (snowflake string)
        text: 전송할 텍스트
        _save: messages.json에 저장 여부
    """
    if not BOT_TOKEN:
        print("[DISCORD] BOT_TOKEN 미설정 — 전송 스킵")
        return False

    try:
        # 2000자 제한 자동 분할 (D1)
        if len(text) <= 1800:
            _send_chunk(channel_id, text)
        else:
            chunks = [text[i:i+1800] for i in range(0, len(text), 1800)]
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(0.3)
                _send_chunk(channel_id, chunk)

        if _save:
            try:
                from ._msg_store import save_bot_response
                msg_id = f"bot_progress_{int(time.time() * 1000)}"
                save_bot_response(channel_id, text, [msg_id], channel="discord")
            except Exception as e:
                print(f"[DISCORD] 봇 응답 저장 실패: {e}")

        return True

    except requests.exceptions.HTTPError as e:
        # Rate limiting
        if e.response is not None and e.response.status_code == 429:
            retry_after = e.response.json().get("retry_after", 1)
            print(f"[DISCORD] Rate limited — {retry_after}s 후 재시도")
            time.sleep(retry_after)
            try:
                # C-5: 전체 텍스트 재전송 (분할 포함)
                chunks = [text[i:i+1800] for i in range(0, len(text), 1800)]
                for i, chunk in enumerate(chunks):
                    if i > 0:
                        time.sleep(0.3)
                    _send_chunk(channel_id, chunk)
                return True
            except Exception:
                pass
        print(f"[DISCORD] 메시지 전송 실패: {e}")
        return False
    except Exception as e:
        print(f"[DISCORD] 메시지 전송 실패: {e}")
        return False


def send_files_sync(channel_id, text, file_paths, **kwargs):
    """Discord 파일 전송 (동기).

    Args:
        channel_id: Discord 채널 ID
        text: 메시지 텍스트
        file_paths: 파일 경로 리스트
    """
    if not BOT_TOKEN:
        return False

    # 텍스트 먼저 전송
    if text:
        send_message_sync(channel_id, text, _save=False)

    session = _get_session()
    try:
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"[DISCORD] 파일 없음: {file_path}")
                continue

            # 25MB 제한 체크 (D2)
            file_size = os.path.getsize(file_path)
            if file_size > 25_000_000:
                print(f"[DISCORD] 파일 크기 초과 (25MB): {os.path.basename(file_path)}")
                send_message_sync(
                    channel_id,
                    f"파일이 25MB를 초과합니다: {os.path.basename(file_path)} ({file_size // 1024 // 1024}MB)",
                    _save=False,
                )
                continue

            with open(file_path, "rb") as f:
                resp = session.post(
                    f"{API_BASE}/channels/{channel_id}/messages",
                    data={"content": ""},
                    files={"file": (os.path.basename(file_path), f)},
                    timeout=30,
                )
                resp.raise_for_status()
            time.sleep(0.3)

        return True
    except Exception as e:
        print(f"[DISCORD] 파일 전송 실패: {e}")
        return False
