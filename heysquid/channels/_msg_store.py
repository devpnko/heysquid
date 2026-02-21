"""
heysquid.channels._msg_store — messages.json I/O.

Functions:
- load_telegram_messages / save_telegram_messages
- save_bot_response
- _safe_parse_timestamp, _cleanup_old_messages
- _poll_telegram_once
"""

import os
import json
import fcntl
import tempfile
from datetime import datetime, timedelta

from ..paths import MESSAGES_FILE, DATA_DIR

_LOCK_PATH = MESSAGES_FILE + '.lock'


def load_telegram_messages():
    """messages.json 로드"""
    if not os.path.exists(MESSAGES_FILE):
        return {"messages": [], "last_update_id": 0}

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] messages.json 읽기 오류: {e}")
        return {"messages": [], "last_update_id": 0}


def save_telegram_messages(data):
    """messages.json 원자적 저장 (tmp + fsync + rename)"""
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=DATA_DIR, suffix='.json.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, MESSAGES_FILE)
    except Exception:
        # 실패 시 임시 파일 정리
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_and_modify(modifier_fn):
    """messages.json을 잠금 하에 읽기-수정-쓰기 (fcntl.flock)

    Args:
        modifier_fn: data dict를 받아 수정된 data dict를 반환하는 함수
    Returns:
        modifier_fn의 반환값
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(_LOCK_PATH, 'w') as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            data = load_telegram_messages()
            result = modifier_fn(data)
            save_telegram_messages(result)
            return result
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def save_bot_response(chat_id, text, reply_to_message_ids, files=None, channel="system"):
    """봇 응답을 messages.json에 저장 (대화 컨텍스트 유지) — flock 사용"""
    bot_message = {
        "message_id": f"bot_{reply_to_message_ids[0]}",
        "type": "bot",
        "channel": channel,
        "chat_id": chat_id,
        "text": text,
        "files": files or [],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reply_to": reply_to_message_ids,
        "processed": True
    }

    def _append_bot_msg(data):
        data["messages"].append(bot_message)
        return data

    load_and_modify(_append_bot_msg)
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
    from .telegram import run_async_safe
    try:
        run_async_safe(fetch_new_messages())
    except Exception as e:
        print(f"[WARN] 폴링 중 오류: {e}")
