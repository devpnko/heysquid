"""
heysquid._msg_store — telegram_messages.json I/O.

Functions:
- load_telegram_messages / save_telegram_messages
- save_bot_response
- _safe_parse_timestamp, _cleanup_old_messages
- _poll_telegram_once
"""

import os
import json
from datetime import datetime, timedelta

from .paths import MESSAGES_FILE, DATA_DIR


def load_telegram_messages():
    """telegram_messages.json 로드"""
    if not os.path.exists(MESSAGES_FILE):
        return {"messages": [], "last_update_id": 0}

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] telegram_messages.json 읽기 오류: {e}")
        return {"messages": [], "last_update_id": 0}


def save_telegram_messages(data):
    """telegram_messages.json 저장"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_bot_response(chat_id, text, reply_to_message_ids, files=None):
    """봇 응답을 telegram_messages.json에 저장 (대화 컨텍스트 유지)"""
    data = load_telegram_messages()

    bot_message = {
        "message_id": f"bot_{reply_to_message_ids[0]}",
        "type": "bot",
        "chat_id": chat_id,
        "text": text,
        "files": files or [],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reply_to": reply_to_message_ids,
        "processed": True
    }

    data["messages"].append(bot_message)
    save_telegram_messages(data)
    print(f"[LOG] 봇 응답 저장 완료 (reply_to: {reply_to_message_ids})")


def _safe_parse_timestamp(ts):
    """타임스탬프 파싱. 실패 시 None 반환."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _cleanup_old_messages():
    """30일 초과 처리된 메시지 정리"""
    data = load_telegram_messages()
    messages = data.get("messages", [])

    cutoff = datetime.now() - timedelta(days=30)

    cleaned = [
        msg for msg in messages
        if not msg.get("processed", False)
        or (_safe_parse_timestamp(msg.get("timestamp", "")) or datetime.now()) > cutoff
    ]

    removed = len(messages) - len(cleaned)
    if removed > 0:
        data["messages"] = cleaned
        save_telegram_messages(data)
        print(f"[CLEAN] 30일 초과 메시지 {removed}개 정리 완료")


def _poll_telegram_once():
    """Telegram API에서 새 메시지를 한 번 가져와서 json 업데이트"""
    from .telegram_listener import fetch_new_messages
    from .telegram_sender import run_async_safe
    try:
        run_async_safe(fetch_new_messages())
    except Exception as e:
        print(f"[WARN] 폴링 중 오류: {e}")
