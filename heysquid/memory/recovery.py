"""
heysquid.memory.recovery — crash recovery & interrupt detection.

Functions:
- check_crash_recovery
- check_interrupted
"""

import os
import json

from ..paths import WORKING_LOCK_FILE, INTERRUPTED_FILE
from .._msg_store import load_telegram_messages


def check_crash_recovery():
    """
    세션 시작 시 — 이전 세션이 작업 중 비정상 종료되었는지 확인.

    working.json이 남아있으면 이전 세션이 작업 중 죽은 것.
    복구 정보를 반환하고, working.json을 정리한다.

    Returns:
        dict or None: 복구 정보
        {
            "crashed": True,
            "instruction": "작업 내용 요약",
            "message_ids": [...],
            "chat_id": ...,
            "started_at": "시작 시각",
            "original_messages": [원본 메시지들]
        }
    """
    if not os.path.exists(WORKING_LOCK_FILE):
        return None

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
    except Exception as e:
        print(f"[WARN] working.json 읽기 오류: {e}")
        os.remove(WORKING_LOCK_FILE)
        return None

    # 복구 정보 구성
    message_ids = lock_info.get("message_id")
    if not isinstance(message_ids, list):
        message_ids = [message_ids]

    instruction = lock_info.get("instruction_summary", "")
    started_at = lock_info.get("started_at", "")

    # 원본 메시지 텍스트 복원
    data = load_telegram_messages()
    messages = data.get("messages", [])
    original_messages = []
    chat_id = None

    for msg in messages:
        if msg.get("message_id") in message_ids:
            original_messages.append({
                "message_id": msg["message_id"],
                "text": msg.get("text", ""),
                "timestamp": msg.get("timestamp", ""),
                "files": msg.get("files", [])
            })
            if not chat_id:
                chat_id = msg.get("chat_id")

    # working.json 정리
    os.remove(WORKING_LOCK_FILE)
    print(f"[RECOVERY] 이전 세션 비정상 종료 감지!")
    print(f"  작업: {instruction}")
    print(f"  시작: {started_at}")
    print(f"  메시지 {len(message_ids)}개 복구")

    return {
        "crashed": True,
        "instruction": instruction,
        "message_ids": message_ids,
        "chat_id": chat_id,
        "started_at": started_at,
        "original_messages": original_messages
    }


def check_interrupted():
    """
    세션 시작 시 — 사용자가 이전 작업을 중단했는지 확인.

    interrupted.json이 있으면 사용자가 의도적으로 중단한 것.
    정보를 반환하고, interrupted.json을 삭제한다.

    Returns:
        dict or None: 중단 정보
        {
            "interrupted": True,
            "interrupted_at": "시각",
            "reason": "멈춰",
            "previous_work": {"instruction": "...", ...} or None,
            "chat_id": ...
        }
    """
    if not os.path.exists(INTERRUPTED_FILE):
        return None

    try:
        with open(INTERRUPTED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[WARN] interrupted.json 읽기 오류: {e}")
        try:
            os.remove(INTERRUPTED_FILE)
        except OSError:
            pass
        return None

    # interrupted.json 정리
    os.remove(INTERRUPTED_FILE)

    prev = data.get("previous_work")
    if prev:
        print(f"[INTERRUPTED] 사용자 중단 감지!")
        print(f"  중단 시각: {data.get('interrupted_at')}")
        print(f"  이전 작업: {prev.get('instruction')}")
    else:
        print(f"[INTERRUPTED] 사용자 중단 감지 (진행 중 작업 없었음)")

    data["interrupted"] = True
    return data
