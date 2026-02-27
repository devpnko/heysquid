"""
heysquid.core._working_lock — working lock + dashboard logging + mid-work message detection.

Functions:
- _dashboard_log
- check_working_lock, create_working_lock, update_working_activity, remove_working_lock
- check_new_messages_during_work, save_new_instructions, load_new_instructions, clear_new_instructions
"""

import os
import json
import time
from datetime import datetime

from .paths import (
    DATA_DIR,
    WORKING_LOCK_FILE,
    NEW_INSTRUCTIONS_FILE,
    WORKING_LOCK_TIMEOUT,
)
from ..channels._msg_store import load_telegram_messages, _poll_telegram_once


def _dashboard_log(agent, message):
    """Add mission log entry to dashboard + kanban activity (silent fail).

    Batched: mission_log + pm.speech in 1 flock on agent_status.json,
    kanban activity in 1 flock on kanban.json. Total: 2 flocks (was 3).
    """
    try:
        from ..dashboard import add_mission_log_and_speech
        add_mission_log_and_speech(agent, message)
    except Exception:
        pass
    try:
        from ..dashboard.kanban import log_agent_activity
        log_agent_activity(agent, message)
    except Exception:
        pass


def check_working_lock():
    """
    Check working lock file. 30-minute timeout based on last activity.

    Returns:
        dict or None: Lock info (if exists) or None
        Special case: {"stale": True, ...} - stale task
    """
    if not os.path.exists(WORKING_LOCK_FILE):
        return None

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
    except Exception as e:
        print(f"[WARN] Error reading working.json: {e}")
        return None

    last_activity_str = lock_info.get("last_activity", lock_info.get("started_at"))

    try:
        last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        idle_seconds = (now - last_activity).total_seconds()

        if idle_seconds > WORKING_LOCK_TIMEOUT:
            print(f"[WARN] Stale task detected (last activity: {int(idle_seconds/60)} min ago)")
            print(f"   Message ID: {lock_info.get('message_id')}")
            print(f"   Instruction: {lock_info.get('instruction_summary')}")
            lock_info["stale"] = True
            return lock_info

        print(f"[INFO] Task in progress (last activity: {int(idle_seconds/60)} min ago)")
        return lock_info

    except Exception as e:
        print(f"[WARN] Timestamp parsing error: {e}")
        lock_age = time.time() - os.path.getmtime(WORKING_LOCK_FILE)
        if lock_age > WORKING_LOCK_TIMEOUT:
            try:
                os.remove(WORKING_LOCK_FILE)
            except OSError:
                pass
            return None
        return lock_info


def create_working_lock(message_id, instruction, chat_id=None):
    """Atomically create working lock file."""
    if isinstance(message_id, list):
        message_ids = message_id
        msg_id_str = f"{', '.join(map(str, message_ids))} (combined {len(message_ids)} messages)"
    else:
        message_ids = [message_id]
        msg_id_str = str(message_id)

    summary = instruction.replace("\n", " ")[:50]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lock_data = {
        "message_id": message_ids[0] if len(message_ids) == 1 else message_ids,
        "instruction_summary": summary,
        "started_at": now_str,
        "last_activity": now_str,
        "count": len(message_ids),
        "chat_id": chat_id,
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        with open(WORKING_LOCK_FILE, "x", encoding="utf-8") as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)
        print(f"[LOCK] Working lock created: message_id={msg_id_str}")
        _dashboard_log('pm', f'Starting: {summary}')

        # Kanban: move to In Progress (auto-create if not found)
        try:
            from ..dashboard.kanban import update_kanban_by_message_ids, add_kanban_task, COL_IN_PROGRESS, COL_TODO
            moved = update_kanban_by_message_ids(message_ids, COL_IN_PROGRESS)
            if not moved:
                # Card not found -> create TODO then immediately move to IN_PROGRESS
                add_kanban_task(
                    title=summary,
                    column=COL_IN_PROGRESS,
                    source_message_ids=message_ids,
                    chat_id=chat_id,
                )
        except Exception:
            pass

        # Start typing indicator
        try:
            from ..channels._typing import start as _typing_start
            _typing_start(chat_id)
        except Exception:
            pass

        return True
    except FileExistsError:
        print(f"[WARN] Lock file already exists. Another task is in progress.")
        return False


def update_working_activity():
    """Update the last activity timestamp of the working lock"""
    if not os.path.exists(WORKING_LOCK_FILE):
        return

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_data = json.load(f)

        lock_data["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(WORKING_LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[WARN] Error updating working.json activity: {e}")


def check_new_messages_during_work():
    """Check for new messages during work"""
    if not os.path.exists(WORKING_LOCK_FILE):
        return []

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
    except Exception:
        return []

    if lock_info.get("stale"):
        return []

    current_message_ids = lock_info.get("message_id")
    if not isinstance(current_message_ids, list):
        current_message_ids = [current_message_ids]

    already_saved = load_new_instructions()
    saved_message_ids = {inst["message_id"] for inst in already_saved}

    _poll_telegram_once()

    data = load_telegram_messages()
    messages = data.get("messages", [])

    new_messages = []
    for msg in messages:
        if msg.get("processed", False):
            continue
        if msg["message_id"] in current_message_ids:
            continue
        if msg["message_id"] in saved_message_ids:
            continue

        new_messages.append({
            "message_id": msg["message_id"],
            "instruction": msg["text"],
            "timestamp": msg["timestamp"],
            "chat_id": msg["chat_id"],
            "user_name": msg["first_name"],
            "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return new_messages


def save_new_instructions(new_messages):
    """Save new instructions to file"""
    if not new_messages:
        return

    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(NEW_INSTRUCTIONS_FILE):
        try:
            with open(NEW_INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"instructions": []}
    else:
        data = {"instructions": []}

    existing_ids = {inst["message_id"] for inst in data["instructions"]}
    for msg in new_messages:
        if msg["message_id"] not in existing_ids:
            data["instructions"].append(msg)

    with open(NEW_INSTRUCTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"[SAVE] New instructions saved: {len(new_messages)}")


def load_new_instructions():
    """Read saved new instructions"""
    if not os.path.exists(NEW_INSTRUCTIONS_FILE):
        return []

    try:
        with open(NEW_INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("instructions", [])
    except Exception as e:
        print(f"[WARN] Error reading new_instructions.json: {e}")
        return []


def clear_new_instructions():
    """Delete new instructions file"""
    if os.path.exists(NEW_INSTRUCTIONS_FILE):
        try:
            os.remove(NEW_INSTRUCTIONS_FILE)
            print("[CLEAN] New instructions file cleaned up")
        except OSError as e:
            print(f"[WARN] Error deleting new_instructions.json: {e}")


def remove_working_lock(transition_to_waiting=False):
    """Delete working lock file.

    Args:
        transition_to_waiting: If True, transition to WAITING state (allow other TODOs to be processed).
            Only changes log message, pm.speech is preserved.
    """
    # Stop typing indicator before removing lock
    try:
        from ..channels._typing import stop as _typing_stop
        _typing_stop()
    except Exception:
        pass

    if os.path.exists(WORKING_LOCK_FILE):
        os.remove(WORKING_LOCK_FILE)
        if transition_to_waiting:
            print("[UNLOCK] Working lock released (WAITING transition)")
            _dashboard_log('pm', 'Waiting for feedback...')
        else:
            print("[UNLOCK] Working lock released")
            _dashboard_log('pm', 'Standing by...')
            try:
                from ..dashboard import set_pm_speech
                set_pm_speech('')  # Clear pm.speech so idle lines can play
            except Exception:
                pass
