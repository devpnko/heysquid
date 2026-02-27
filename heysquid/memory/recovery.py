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
    Called at session start — checks if the previous session terminated abnormally while working.

    If working.json still exists, the previous session died mid-task.
    Returns recovery info and cleans up working.json.

    Returns:
        dict or None: Recovery info
        {
            "crashed": True,
            "instruction": "task summary",
            "message_ids": [...],
            "chat_id": ...,
            "started_at": "start time",
            "original_messages": [original messages]
        }
    """
    if not os.path.exists(WORKING_LOCK_FILE):
        return None

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
    except Exception as e:
        print(f"[WARN] Error reading working.json: {e}")
        os.remove(WORKING_LOCK_FILE)
        return None

    # Build recovery info
    message_ids = lock_info.get("message_id")
    if not isinstance(message_ids, list):
        message_ids = [message_ids]

    instruction = lock_info.get("instruction_summary", "")
    started_at = lock_info.get("started_at", "")

    # Restore original message text
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

    # Clean up working.json
    os.remove(WORKING_LOCK_FILE)
    print(f"[RECOVERY] Previous session abnormal termination detected!")
    print(f"  Task: {instruction}")
    print(f"  Started: {started_at}")
    print(f"  Recovering {len(message_ids)} message(s)")

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
    Called at session start — checks if the user interrupted a previous task.

    If interrupted.json exists, the user intentionally stopped the task.
    Returns the interruption info and deletes interrupted.json.

    Returns:
        dict or None: Interruption info
        {
            "interrupted": True,
            "interrupted_at": "timestamp",
            "reason": "stop",
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
        print(f"[WARN] Error reading interrupted.json: {e}")
        try:
            os.remove(INTERRUPTED_FILE)
        except OSError:
            pass
        return None

    # Clean up interrupted.json
    os.remove(INTERRUPTED_FILE)

    prev = data.get("previous_work")
    if prev:
        print(f"[INTERRUPTED] User interruption detected!")
        print(f"  Interrupted at: {data.get('interrupted_at')}")
        print(f"  Previous task: {prev.get('instruction')}")
    else:
        print(f"[INTERRUPTED] User interruption detected (no work was in progress)")

    data["interrupted"] = True
    return data
