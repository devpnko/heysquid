"""
heysquid.channels.slack — Slack sender (WebClient 기반).

역할:
- PM 응답 및 브로드캐스트 메시지를 Slack으로 전송
- 파일 업로드
- Markdown → mrkdwn 자동 변환

사용법:
    from heysquid.channels.slack import send_message_sync, send_files_sync
"""

import os
import re
import time

from dotenv import load_dotenv

from ..config import get_env_path

load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

# WebClient 싱글턴 (lazy init)
_client = None


def _get_client():
    """WebClient 인스턴스 재사용"""
    global _client
    if _client is None:
        from slack_sdk import WebClient
        _client = WebClient(token=BOT_TOKEN)
    return _client


def _markdown_to_mrkdwn(text):
    """Markdown → Slack mrkdwn 변환.

    변환 규칙:
    - **bold** → *bold*
    - 나머지 (italic, code, link)는 동일하거나 호환
    """
    # **bold** → *bold* (이미 *single*이면 유지)
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    return text


def send_message_sync(channel_id, text, _save=True, thread_ts=None, **kwargs):
    """Slack 메시지 전송 (동기).

    Args:
        channel_id: Slack 채널/DM ID
        text: 전송할 텍스트
        _save: messages.json에 저장 여부 (브로드캐스트 시 False)
        thread_ts: 스레드 응답 시 원본 메시지 ts
    """
    if not BOT_TOKEN:
        print("[SLACK] BOT_TOKEN 미설정 — 전송 스킵")
        return False

    try:
        client = _get_client()
        mrkdwn_text = _markdown_to_mrkdwn(text)

        # Slack 메시지 길이 제한: 40,000자이지만 가독성 위해 3,000자 분할
        if len(mrkdwn_text) > 3000:
            chunks = [mrkdwn_text[i:i+3000] for i in range(0, len(mrkdwn_text), 3000)]
            for i, chunk in enumerate(chunks):
                if i > 0:
                    time.sleep(0.3)
                client.chat_postMessage(
                    channel=channel_id,
                    text=chunk,
                    thread_ts=thread_ts,
                )
        else:
            client.chat_postMessage(
                channel=channel_id,
                text=mrkdwn_text,
                thread_ts=thread_ts,
            )

        if _save:
            try:
                from ._msg_store import save_bot_response
                msg_id = f"bot_progress_{int(time.time() * 1000)}"
                save_bot_response(channel_id, text, [msg_id], channel="slack")
            except Exception as e:
                print(f"[SLACK] 봇 응답 저장 실패: {e}")

        return True

    except Exception as e:
        # Rate limiting 처리 (S6)
        err_str = str(e)
        if "ratelimited" in err_str:
            retry_after = 1
            try:
                retry_after = int(getattr(e, 'response', {}).get('headers', {}).get('Retry-After', 1))
            except (AttributeError, ValueError, TypeError):
                pass
            print(f"[SLACK] Rate limited — {retry_after}s 후 재시도")
            time.sleep(retry_after)
            try:
                client = _get_client()
                client.chat_postMessage(
                    channel=channel_id,
                    text=_markdown_to_mrkdwn(text),
                    thread_ts=thread_ts,
                )
                return True
            except Exception as retry_err:
                print(f"[SLACK] 재시도 실패: {retry_err}")
                return False
        print(f"[SLACK] 메시지 전송 실패: {e}")
        return False


def send_files_sync(channel_id, text, file_paths, **kwargs):
    """Slack 파일 업로드 (동기).

    Args:
        channel_id: Slack 채널/DM ID
        text: 메시지 텍스트
        file_paths: 파일 경로 리스트
    """
    if not BOT_TOKEN:
        return False

    # 텍스트 먼저 전송
    if text:
        send_message_sync(channel_id, text, _save=False)

    try:
        client = _get_client()
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"[SLACK] 파일 없음: {file_path}")
                continue
            client.files_upload_v2(
                channel=channel_id,
                file=file_path,
                title=os.path.basename(file_path),
            )
            time.sleep(0.3)
        return True
    except Exception as e:
        print(f"[SLACK] 파일 전송 실패: {e}")
        return False
