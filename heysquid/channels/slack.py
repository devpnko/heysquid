"""
heysquid.channels.slack — Slack sender (WebClient-based).

Responsibilities:
- Send PM responses and broadcast messages to Slack
- File upload
- Automatic Markdown → mrkdwn conversion

Usage:
    from heysquid.channels.slack import send_message_sync, send_files_sync
"""

import os
import re
import time

from dotenv import load_dotenv

from ..config import get_env_path

load_dotenv(get_env_path())

BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

# WebClient singleton (lazy init)
_client = None


def _get_client():
    """Reuse WebClient instance"""
    global _client
    if _client is None:
        from slack_sdk import WebClient
        _client = WebClient(token=BOT_TOKEN)
    return _client


def _markdown_to_mrkdwn(text):
    """Markdown → Slack mrkdwn conversion.

    Conversion rules:
    - **bold** → *bold*
    - Others (italic, code, link) are identical or compatible
    """
    # **bold** → *bold* (keep *single* as-is)
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    return text


def send_message_sync(channel_id, text, _save=True, thread_ts=None, **kwargs):
    """Slack message send (synchronous).

    Args:
        channel_id: Slack channel/DM ID
        text: Text to send
        _save: Whether to save to messages.json (False for broadcasts)
        thread_ts: Original message ts for threaded replies
    """
    if not BOT_TOKEN:
        print("[SLACK] BOT_TOKEN not set — skipping send")
        return False

    try:
        client = _get_client()
        mrkdwn_text = _markdown_to_mrkdwn(text)

        # Slack message limit: 40,000 chars, but split at 3,000 for readability
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
                print(f"[SLACK] Failed to save bot response: {e}")

        return True

    except Exception as e:
        # Rate limiting handling (S6)
        err_str = str(e)
        if "ratelimited" in err_str:
            retry_after = 1
            try:
                retry_after = int(getattr(e, 'response', {}).get('headers', {}).get('Retry-After', 1))
            except (AttributeError, ValueError, TypeError):
                pass
            print(f"[SLACK] Rate limited — retrying in {retry_after}s")
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
                print(f"[SLACK] Retry failed: {retry_err}")
                return False
        print(f"[SLACK] Message send failed: {e}")
        return False


def send_files_sync(channel_id, text, file_paths, **kwargs):
    """Slack file upload (synchronous).

    Args:
        channel_id: Slack channel/DM ID
        text: Message text
        file_paths: List of file paths
    """
    if not BOT_TOKEN:
        return False

    # Send text first
    if text:
        send_message_sync(channel_id, text, _save=False)

    try:
        client = _get_client()
        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"[SLACK] File not found: {file_path}")
                continue
            client.files_upload_v2(
                channel=channel_id,
                file=file_path,
                title=os.path.basename(file_path),
            )
            time.sleep(0.3)
        return True
    except Exception as e:
        print(f"[SLACK] File send failed: {e}")
        return False
