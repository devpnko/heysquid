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
    작업 잠금 파일 확인. 마지막 활동 기준 30분 타임아웃.

    Returns:
        dict or None: 잠금 정보 (존재하면) 또는 None
        특수 케이스: {"stale": True, ...} - 스탈 작업
    """
    if not os.path.exists(WORKING_LOCK_FILE):
        return None

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_info = json.load(f)
    except Exception as e:
        print(f"[WARN] working.json 읽기 오류: {e}")
        return None

    last_activity_str = lock_info.get("last_activity", lock_info.get("started_at"))

    try:
        last_activity = datetime.strptime(last_activity_str, "%Y-%m-%d %H:%M:%S")
        now = datetime.now()
        idle_seconds = (now - last_activity).total_seconds()

        if idle_seconds > WORKING_LOCK_TIMEOUT:
            print(f"[WARN] 스탈 작업 감지 (마지막 활동: {int(idle_seconds/60)}분 전)")
            print(f"   메시지 ID: {lock_info.get('message_id')}")
            print(f"   지시사항: {lock_info.get('instruction_summary')}")
            lock_info["stale"] = True
            return lock_info

        print(f"[INFO] 작업 진행 중 (마지막 활동: {int(idle_seconds/60)}분 전)")
        return lock_info

    except Exception as e:
        print(f"[WARN] 타임스탬프 파싱 오류: {e}")
        lock_age = time.time() - os.path.getmtime(WORKING_LOCK_FILE)
        if lock_age > WORKING_LOCK_TIMEOUT:
            try:
                os.remove(WORKING_LOCK_FILE)
            except OSError:
                pass
            return None
        return lock_info


def create_working_lock(message_id, instruction, chat_id=None):
    """원자적으로 작업 잠금 파일 생성."""
    if isinstance(message_id, list):
        message_ids = message_id
        msg_id_str = f"{', '.join(map(str, message_ids))} (합산 {len(message_ids)}개)"
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
        print(f"[LOCK] 작업 잠금 생성: message_id={msg_id_str}")
        _dashboard_log('pm', f'Starting: {summary}')

        # Kanban: move to In Progress (없으면 자동 생성)
        try:
            from ..dashboard.kanban import update_kanban_by_message_ids, add_kanban_task, COL_IN_PROGRESS, COL_TODO
            moved = update_kanban_by_message_ids(message_ids, COL_IN_PROGRESS)
            if not moved:
                # 카드가 없음 → TODO 생성 후 즉시 IN_PROGRESS
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
        print(f"[WARN] 잠금 파일 이미 존재. 다른 작업이 진행 중입니다.")
        return False


def update_working_activity():
    """작업 잠금의 마지막 활동 시각 갱신"""
    if not os.path.exists(WORKING_LOCK_FILE):
        return

    try:
        with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
            lock_data = json.load(f)

        lock_data["last_activity"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with open(WORKING_LOCK_FILE, "w", encoding="utf-8") as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"[WARN] working.json 활동 갱신 오류: {e}")


def check_new_messages_during_work():
    """작업 중 새 메시지 확인"""
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
    """새 지시사항을 파일에 저장"""
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

    print(f"[SAVE] 새 지시사항 저장: {len(new_messages)}개")


def load_new_instructions():
    """저장된 새 지시사항 읽기"""
    if not os.path.exists(NEW_INSTRUCTIONS_FILE):
        return []

    try:
        with open(NEW_INSTRUCTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("instructions", [])
    except Exception as e:
        print(f"[WARN] new_instructions.json 읽기 오류: {e}")
        return []


def clear_new_instructions():
    """새 지시사항 파일 삭제"""
    if os.path.exists(NEW_INSTRUCTIONS_FILE):
        try:
            os.remove(NEW_INSTRUCTIONS_FILE)
            print("[CLEAN] 새 지시사항 파일 정리 완료")
        except OSError as e:
            print(f"[WARN] new_instructions.json 삭제 오류: {e}")


def remove_working_lock(transition_to_waiting=False):
    """작업 잠금 파일 삭제.

    Args:
        transition_to_waiting: True면 WAITING 상태 전환 (다른 TODO 처리 가능하게).
            로그 메시지만 변경, pm.speech는 유지.
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
            print("[UNLOCK] 작업 잠금 해제 (WAITING 전환)")
            _dashboard_log('pm', 'Waiting for feedback...')
        else:
            print("[UNLOCK] 작업 잠금 해제")
            _dashboard_log('pm', 'Standing by...')
            try:
                from ..dashboard import set_pm_speech
                set_pm_speech('')  # Clear pm.speech so idle lines can play
            except Exception:
                pass
