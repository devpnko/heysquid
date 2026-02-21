"""
heysquid.channels._msg_store — messages.json I/O.

Functions:
- load_telegram_messages / save_telegram_messages
- save_bot_response
- get_cursor / set_cursor  (멀티채널 cursor 관리)
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


def _default_data():
    return {"messages": [], "last_update_id": 0, "cursors": {}}


def _migrate_cursors(data):
    """last_update_id → cursors.telegram 마이그레이션 (하위 호환)"""
    if "cursors" not in data:
        data["cursors"] = {}
    # 기존 last_update_id가 있고 cursors.telegram이 없으면 이동
    old_id = data.get("last_update_id", 0)
    if old_id and "telegram" not in data["cursors"]:
        data["cursors"]["telegram"] = {"last_update_id": old_id}
    return data


def load_telegram_messages():
    """messages.json 로드 (cursors 마이그레이션 포함)"""
    if not os.path.exists(MESSAGES_FILE):
        return _default_data()

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _migrate_cursors(data)
    except Exception as e:
        print(f"[WARN] messages.json 읽기 오류: {e}")
        return _default_data()


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
            # C-7: modifier_fn이 None 반환 시 원본 data 사용 (방어 코드)
            if result is None:
                result = data
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


def get_cursor(channel, key=None):
    """채널별 cursor 값 조회.

    Args:
        channel: "telegram", "slack", "discord"
        key: cursor 내 특정 키 (예: "last_update_id"). None이면 채널 cursor dict 전체.
    """
    data = load_telegram_messages()
    ch_cursor = data.get("cursors", {}).get(channel, {})
    # 하위 호환: telegram의 경우 top-level last_update_id도 확인
    if channel == "telegram" and not ch_cursor:
        ch_cursor = {"last_update_id": data.get("last_update_id", 0)}
    if key:
        return ch_cursor.get(key, 0)
    return ch_cursor


def set_cursor(channel, key, value):
    """채널별 cursor 값 설정 (flock atomic).

    Args:
        channel: "telegram", "slack", "discord"
        key: cursor 내 키 (예: "last_update_id")
        value: 설정할 값
    """
    def _update_cursor(data):
        data = _migrate_cursors(data)
        if channel not in data["cursors"]:
            data["cursors"][channel] = {}
        data["cursors"][channel][key] = value
        # 하위 호환: telegram은 top-level에도 동기화
        if channel == "telegram" and key == "last_update_id":
            data["last_update_id"] = value
        return data
    load_and_modify(_update_cursor)


def _safe_parse_timestamp(ts):
    """타임스탬프 파싱. 실패 시 None 반환."""
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return None


def _cleanup_old_messages():
    """30일 초과 처리된 메시지 정리 (C-1: load_and_modify로 통일 — flock atomic)"""
    cutoff = datetime.now() - timedelta(days=30)

    def _do_cleanup(data):
        messages = data.get("messages", [])
        cleaned = [
            msg for msg in messages
            if not msg.get("processed", False)
            or (_safe_parse_timestamp(msg.get("timestamp", "")) or datetime.now()) > cutoff
        ]
        removed = len(messages) - len(cleaned)
        if removed > 0:
            data["messages"] = cleaned
            print(f"[CLEAN] 30일 초과 메시지 {removed}개 정리 완료")
        return data

    load_and_modify(_do_cleanup)


def _poll_telegram_once():
    """Telegram API에서 새 메시지를 한 번 가져와서 json 업데이트"""
    from .telegram_listener import fetch_new_messages
    from .telegram import run_async_safe
    try:
        run_async_safe(fetch_new_messages())
    except Exception as e:
        print(f"[WARN] 폴링 중 오류: {e}")
