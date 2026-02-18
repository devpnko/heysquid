"""
텔레그램 봇 통합 로직 — heysquid Mac 포팅

주요 기능:
- check_telegram() - 새로운 명령 확인 (최근 24시간 대화 내역 포함)
- report_telegram() - 결과 전송 및 메모리 저장
- mark_done_telegram() - 처리 완료 표시
- load_memory() - 기존 메모리 로드
- reserve_memory_telegram() - 작업 시작 시 메모리 예약
+ workspace 연동 (switch_workspace on project mention)
"""

import os
import json
import time
from datetime import datetime, timedelta
from telegram_sender import send_files_sync, run_async_safe

def _dashboard_log(agent, message):
    """Add mission log entry to dashboard (silent fail)."""
    try:
        from agent_dashboard import add_mission_log, update_agent_status, set_pm_speech
        add_mission_log(agent, message)
        if agent == 'pm':
            set_pm_speech(message)
    except Exception:
        pass

# 경로 설정 (Mac)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
TASKS_DIR = os.path.join(PROJECT_ROOT, "tasks")
INDEX_FILE = os.path.join(TASKS_DIR, "index.json")

MESSAGES_FILE = os.path.join(DATA_DIR, "telegram_messages.json")
WORKING_LOCK_FILE = os.path.join(DATA_DIR, "working.json")
NEW_INSTRUCTIONS_FILE = os.path.join(DATA_DIR, "new_instructions.json")
INTERRUPTED_FILE = os.path.join(DATA_DIR, "interrupted.json")
SESSION_MEMORY_FILE = os.path.join(DATA_DIR, "session_memory.md")
SESSION_MEMORY_MAX_CONVERSATIONS = 50  # 최근 대화 최대 항목 수
WORKING_LOCK_TIMEOUT = 1800  # 30분


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


def reply_telegram(chat_id, message_id, text):
    """
    자연스러운 대화 응답 (가벼운 대화용)

    - send_message_sync()로 전송
    - save_bot_response()로 대화 기록 저장
    - processed = True 표시
    - working lock/memory 없음 (가벼운 대화에는 불필요)

    Args:
        chat_id: 텔레그램 채팅 ID
        message_id: 응답 대상 메시지 ID (int 또는 list)
        text: 응답 텍스트
    Returns:
        bool: 전송 성공 여부
    """
    from telegram_sender import send_message_sync

    success = send_message_sync(chat_id, text)

    ids = message_id if isinstance(message_id, list) else [message_id]

    if success:
        save_bot_response(chat_id, text, ids)

    # 메시지 processed 표시
    data = load_telegram_messages()
    for msg in data.get("messages", []):
        if msg["message_id"] in ids:
            msg["processed"] = True
    save_telegram_messages(data)

    return success


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


def create_working_lock(message_id, instruction):
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
        "count": len(message_ids)
    }

    os.makedirs(DATA_DIR, exist_ok=True)

    try:
        with open(WORKING_LOCK_FILE, "x", encoding="utf-8") as f:
            json.dump(lock_data, f, ensure_ascii=False, indent=2)
        print(f"[LOCK] 작업 잠금 생성: message_id={msg_id_str}")
        _dashboard_log('pm', f'Starting: {summary}')
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


def remove_working_lock():
    """작업 잠금 파일 삭제"""
    if os.path.exists(WORKING_LOCK_FILE):
        os.remove(WORKING_LOCK_FILE)
        print("[UNLOCK] 작업 잠금 해제")
        _dashboard_log('pm', 'Standing by...')
        try:
            from agent_dashboard import set_pm_speech
            set_pm_speech('')  # Clear pm.speech so idle lines can play
        except Exception:
            pass


def load_index():
    """인덱스 파일 로드"""
    if not os.path.exists(INDEX_FILE):
        return {"tasks": [], "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] index.json 읽기 오류: {e}")
        return {"tasks": [], "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}


def save_index(index_data):
    """인덱스 파일 저장"""
    os.makedirs(TASKS_DIR, exist_ok=True)
    index_data["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, ensure_ascii=False, indent=2)


def update_index(message_id, instruction, result_summary="", files=None, chat_id=None, timestamp=None):
    """인덱스 업데이트"""
    index = load_index()

    keywords = []
    for word in instruction.split():
        if len(word) >= 2:
            keywords.append(word)
    keywords = list(set(keywords))[:10]

    existing_task = None
    for task in index["tasks"]:
        if task["message_id"] == message_id:
            existing_task = task
            break

    task_data = {
        "message_id": message_id,
        "timestamp": timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "instruction": instruction,
        "keywords": keywords,
        "result_summary": result_summary,
        "files": files or [],
        "chat_id": chat_id,
        "task_dir": os.path.join(TASKS_DIR, f"msg_{message_id}")
    }

    if existing_task:
        existing_task.update(task_data)
    else:
        index["tasks"].append(task_data)

    index["tasks"].sort(key=lambda x: x["message_id"], reverse=True)
    save_index(index)
    print(f"[INDEX] 인덱스 업데이트: message_id={message_id}")


def search_memory(keyword=None, message_id=None):
    """인덱스에서 작업 검색"""
    index = load_index()

    if message_id is not None:
        for task in index["tasks"]:
            if task["message_id"] == message_id:
                return [task]
        return []

    if keyword:
        matches = []
        keyword_lower = keyword.lower()
        for task in index["tasks"]:
            if (keyword_lower in task["instruction"].lower() or
                any(keyword_lower in kw.lower() for kw in task["keywords"])):
                matches.append(task)
        return matches

    return index["tasks"]


def get_task_dir(message_id):
    """메시지 ID 기반 작업 폴더 경로 반환"""
    task_dir = os.path.join(TASKS_DIR, f"msg_{message_id}")
    if not os.path.exists(task_dir):
        os.makedirs(task_dir)
        print(f"[DIR] 작업 폴더 생성: {task_dir}")
    return task_dir


def get_24h_context(messages, current_message_id):
    """최근 24시간 대화 내역 생성"""
    now = datetime.now()
    cutoff_time = now - timedelta(hours=24)

    context_lines = ["=== 최근 24시간 대화 내역 ===\n"]

    for msg in messages:
        if msg.get("type") == "user" and msg["message_id"] == current_message_id:
            break

        msg_time = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
        if msg_time < cutoff_time:
            continue

        msg_type = msg.get("type", "user")

        if msg_type == "user":
            user_name = msg.get("first_name", "사용자")
            text = msg.get("text", "")
            files = msg.get("files", [])
            file_info = f" [첨부: {len(files)}개 파일]" if files else ""
            location = msg.get("location")
            location_info = f" [위치: {location['latitude']}, {location['longitude']}]" if location else ""
            context_lines.append(f"[{msg['timestamp']}] {user_name}: {text}{file_info}{location_info}")

        elif msg_type == "bot":
            text = msg.get("text", "")
            text_preview = text[:150] + "..." if len(text) > 150 else text
            files = msg.get("files", [])
            file_info = f" [전송: {', '.join(files)}]" if files else ""
            context_lines.append(f"[{msg['timestamp']}] heysquid: {text_preview}{file_info}")

    if len(context_lines) == 1:
        return "최근 24시간 이내 대화 내역이 없습니다."

    return "\n".join(context_lines)


def _poll_telegram_once():
    """Telegram API에서 새 메시지를 한 번 가져와서 json 업데이트"""
    from telegram_listener import fetch_new_messages
    try:
        run_async_safe(fetch_new_messages())
    except Exception as e:
        print(f"[WARN] 폴링 중 오류: {e}")


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


def _detect_workspace(instruction):
    """
    지시사항에서 워크스페이스 프로젝트명 감지

    Returns:
        str or None: 감지된 워크스페이스 이름
    """
    try:
        from workspace import list_workspaces
        workspaces = list_workspaces()

        instruction_lower = instruction.lower()
        for name in workspaces:
            if name.lower() in instruction_lower:
                return name
    except Exception:
        pass

    return None


def check_telegram():
    """
    새로운 텔레그램 명령 확인

    Returns:
        list: 대기 중인 지시사항 리스트
    """
    lock_info = check_working_lock()

    if lock_info:
        if lock_info.get("stale"):
            print("[RESTART] 스탈 작업 재시작")

            from telegram_sender import send_message_sync
            message_ids = lock_info.get("message_id")
            if not isinstance(message_ids, list):
                message_ids = [message_ids]

            data = load_telegram_messages()
            messages = data.get("messages", [])
            chat_id = None
            for msg in messages:
                if msg["message_id"] in message_ids:
                    chat_id = msg["chat_id"]
                    break

            if chat_id:
                alert_msg = (
                    "**이전 작업이 중단되었습니다**\n\n"
                    f"지시사항: {lock_info.get('instruction_summary')}...\n"
                    f"시작 시각: {lock_info.get('started_at')}\n"
                    f"마지막 활동: {lock_info.get('last_activity')}\n\n"
                    "처음부터 다시 시작합니다."
                )
                send_message_sync(chat_id, alert_msg)

            try:
                os.remove(WORKING_LOCK_FILE)
                print("[UNLOCK] 스탈 잠금 삭제 완료")
            except OSError:
                pass

            pending = []
            for msg in messages:
                if msg["message_id"] in message_ids and not msg.get("processed", False):
                    instruction = msg.get("text", "")
                    message_id = msg["message_id"]
                    chat_id = msg["chat_id"]
                    timestamp = msg["timestamp"]
                    user_name = msg["first_name"]
                    files = msg.get("files", [])
                    location = msg.get("location")
                    context_24h = get_24h_context(messages, message_id)

                    pending.append({
                        "instruction": instruction,
                        "message_id": message_id,
                        "chat_id": chat_id,
                        "timestamp": timestamp,
                        "context_24h": context_24h,
                        "user_name": user_name,
                        "files": files,
                        "location": location,
                        "stale_resume": True
                    })

            return pending

        print(f"[WARN] 다른 작업이 진행 중입니다: message_id={lock_info.get('message_id')}")
        return []

    _poll_telegram_once()
    _cleanup_old_messages()

    data = load_telegram_messages()
    messages = data.get("messages", [])

    pending = []

    for msg in messages:
        if msg.get("processed", False):
            continue

        instruction = msg.get("text", "")
        message_id = msg["message_id"]
        chat_id = msg["chat_id"]
        timestamp = msg["timestamp"]
        user_name = msg["first_name"]
        files = msg.get("files", [])
        location = msg.get("location")

        context_24h = get_24h_context(messages, message_id)

        # 워크스페이스 감지
        workspace_name = _detect_workspace(instruction)

        pending.append({
            "instruction": instruction,
            "message_id": message_id,
            "chat_id": chat_id,
            "timestamp": timestamp,
            "context_24h": context_24h,
            "user_name": user_name,
            "files": files,
            "location": location,
            "stale_resume": False,
            "workspace": workspace_name
        })

    if pending:
        _dashboard_log('pm', f'Message received ({len(pending)} pending)')

    return pending


def _format_file_size(size_bytes):
    """파일 크기를 사람이 읽기 쉬운 형식으로 변환"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"


def combine_tasks(pending_tasks):
    """여러 미처리 메시지를 하나의 통합 작업으로 합산"""
    if not pending_tasks:
        return None

    sorted_tasks = sorted(pending_tasks, key=lambda x: x['timestamp'])
    is_stale_resume = any(task.get('stale_resume', False) for task in sorted_tasks)

    combined_parts = []

    if is_stale_resume:
        combined_parts.append("[중단된 작업 재시작]")
        combined_parts.append("이전 작업의 진행 상태를 확인한 후, 합리적으로 진행할 것.")
        combined_parts.append("tasks/ 폴더에서 이전 작업 결과물을 확인하고, 이어서 작업할 수 있는 경우 이어서 진행하되,")
        combined_parts.append("처음부터 다시 시작하는 것이 더 안전하다면 처음부터 다시 시작할 것.")
        combined_parts.append("")
        combined_parts.append("---")
        combined_parts.append("")

    all_files = []

    # 워크스페이스 감지 (첫 번째 감지된 것 사용)
    detected_workspace = None
    for task in sorted_tasks:
        if task.get("workspace"):
            detected_workspace = task["workspace"]
            break

    # 워크스페이스 정보 추가
    if detected_workspace:
        try:
            from workspace import get_workspace, switch_workspace
            ws_info = get_workspace(detected_workspace)
            if ws_info:
                context_md = switch_workspace(detected_workspace)
                combined_parts.append(f"[활성 워크스페이스: {detected_workspace}]")
                combined_parts.append(f"프로젝트 경로: {ws_info['path']}")
                combined_parts.append(f"설명: {ws_info.get('description', '')}")
                if context_md:
                    combined_parts.append(f"\n--- 프로젝트 컨텍스트 ---\n{context_md}\n---\n")
                combined_parts.append("")
        except Exception:
            pass

    for i, task in enumerate(sorted_tasks, 1):
        combined_parts.append(f"[요청 {i}] ({task['timestamp']})")

        if task['instruction']:
            combined_parts.append(task['instruction'])

        files = task.get('files', [])
        if files:
            combined_parts.append("")
            combined_parts.append("첨부 파일:")
            for file_info in files:
                file_path = file_info['path']
                file_name = os.path.basename(file_path)
                file_type = file_info['type']
                file_size = _format_file_size(file_info.get('size', 0))

                type_emoji = {
                    'photo': '[IMG]',
                    'document': '[DOC]',
                    'video': '[VID]',
                    'audio': '[AUD]',
                    'voice': '[VOI]'
                }
                emoji = type_emoji.get(file_type, '[FILE]')

                combined_parts.append(f"  {emoji} {file_name} ({file_size})")
                combined_parts.append(f"     경로: {file_path}")

                all_files.append(file_info)

        location = task.get('location')
        if location:
            combined_parts.append("")
            combined_parts.append("위치 정보:")
            combined_parts.append(f"  위도: {location['latitude']}")
            combined_parts.append(f"  경도: {location['longitude']}")
            if 'accuracy' in location:
                combined_parts.append(f"  정확도: +/-{location['accuracy']}m")
            maps_url = f"https://www.google.com/maps?q={location['latitude']},{location['longitude']}"
            combined_parts.append(f"  Google Maps: {maps_url}")

        combined_parts.append("")

    combined_instruction = "\n".join(combined_parts).strip()

    context_24h = sorted_tasks[0]['context_24h']
    if context_24h and context_24h != "최근 24시간 이내 대화 내역이 없습니다.":
        combined_instruction = combined_instruction + "\n\n---\n\n[참고사항]\n" + context_24h

    return {
        "combined_instruction": combined_instruction,
        "message_ids": [task['message_id'] for task in sorted_tasks],
        "chat_id": sorted_tasks[0]['chat_id'],
        "timestamp": sorted_tasks[0]['timestamp'],
        "user_name": sorted_tasks[0]['user_name'],
        "all_timestamps": [task['timestamp'] for task in sorted_tasks],
        "context_24h": context_24h,
        "files": all_files,
        "stale_resume": is_stale_resume,
        "workspace": detected_workspace
    }


def reserve_memory_telegram(instruction, chat_id, timestamp, message_id):
    """작업 시작 시 즉시 메모리 예약"""
    if isinstance(message_id, list):
        message_ids = message_id
        main_message_id = message_ids[0]
        timestamps = timestamp if isinstance(timestamp, list) else [timestamp] * len(message_ids)
    else:
        message_ids = [message_id]
        main_message_id = message_id
        timestamps = [timestamp]

    task_dir = get_task_dir(main_message_id)
    filepath = os.path.join(task_dir, "task_info.txt")

    now = datetime.now()

    if len(message_ids) > 1:
        msg_id_info = f"{', '.join(map(str, message_ids))} (합산 {len(message_ids)}개)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id_info}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜]
{msg_date_info}
[지시] {instruction}
[결과] (작업 진행 중...)
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    update_index(
        message_id=main_message_id,
        instruction=instruction,
        result_summary="(작업 진행 중...)",
        files=[],
        chat_id=chat_id,
        timestamp=timestamps[0]
    )

    for i, (msg_id, ts) in enumerate(zip(message_ids[1:], timestamps[1:]), 2):
        ref_dir = get_task_dir(msg_id)
        ref_file = os.path.join(ref_dir, "task_info.txt")
        ref_content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜] {ts}
[지시] (메인 작업 msg_{main_message_id}에 합산됨)
[참조] tasks/msg_{main_message_id}/
[결과] (작업 진행 중...)
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(msg_{main_message_id}에 합산됨)",
            result_summary="(작업 진행 중...)",
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] 메모리 예약 완료: {task_dir}/task_info.txt")
    if len(message_ids) > 1:
        print(f"   합산 메시지: {len(message_ids)}개 ({', '.join(map(str, message_ids))})")


def report_telegram(instruction, result_text, chat_id, timestamp, message_id, files=None):
    """작업 결과를 텔레그램으로 전송하고 메모리에 저장"""
    if isinstance(message_id, list):
        message_ids = message_id
        main_message_id = message_ids[0]
        timestamps = timestamp if isinstance(timestamp, list) else [timestamp] * len(message_ids)
    else:
        message_ids = [message_id]
        main_message_id = message_id
        timestamps = [timestamp]

    message = result_text

    if files:
        file_names = [os.path.basename(f) for f in files]
        message += f"\n\n📎 {', '.join(file_names)}"

    if len(message_ids) > 1:
        message += f"\n\n_{len(message_ids)}개 메시지 합산 처리_"

    print(f"\n[SEND] 텔레그램으로 결과 전송 중... (chat_id: {chat_id})")
    _dashboard_log('pm', 'Mission complete — sending report')
    success = send_files_sync(chat_id, message, files or [])

    if success:
        print("[OK] 결과 전송 완료!")
        save_bot_response(
            chat_id=chat_id,
            text=message,
            reply_to_message_ids=message_ids,
            files=[os.path.basename(f) for f in (files or [])]
        )
    else:
        print("[ERROR] 결과 전송 실패!")
        result_text = f"[전송 실패] {result_text}"
        files = []

    task_dir = get_task_dir(main_message_id)
    filepath = os.path.join(task_dir, "task_info.txt")

    now = datetime.now()

    if len(message_ids) > 1:
        msg_id_info = f"{', '.join(map(str, message_ids))} (합산 {len(message_ids)}개)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id_info}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜]
{msg_date_info}
[지시] {instruction}
[결과] {result_text}
"""

    if files:
        file_names = [os.path.basename(f) for f in files]
        content += f"[보낸파일] {', '.join(file_names)}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    update_index(
        message_id=main_message_id,
        instruction=instruction,
        result_summary=result_text[:100],
        files=[os.path.basename(f) for f in (files or [])],
        chat_id=chat_id,
        timestamp=timestamps[0]
    )

    for i, (msg_id, ts) in enumerate(zip(message_ids[1:], timestamps[1:]), 2):
        ref_dir = get_task_dir(msg_id)
        ref_file = os.path.join(ref_dir, "task_info.txt")
        ref_content = f"""[시간] {now.strftime("%Y-%m-%d %H:%M:%S")}
[메시지ID] {msg_id}
[출처] Telegram (chat_id: {chat_id})
[메시지날짜] {ts}
[지시] (메인 작업 msg_{main_message_id}에 합산됨)
[참조] tasks/msg_{main_message_id}/
[결과] {result_text[:100]}...
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(msg_{main_message_id}에 합산됨)",
            result_summary=result_text[:100],
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] 메모리 저장 완료: {task_dir}/task_info.txt")


def mark_done_telegram(message_id):
    """텔레그램 메시지 처리 완료 표시"""
    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    new_instructions = load_new_instructions()
    if new_instructions:
        print(f"[LOG] 작업 중 추가된 지시사항 {len(new_instructions)}개 함께 처리")
        for inst in new_instructions:
            message_ids.append(inst["message_id"])

    data = load_telegram_messages()
    messages = data.get("messages", [])

    for msg in messages:
        if msg["message_id"] in message_ids:
            msg["processed"] = True

    save_telegram_messages(data)
    clear_new_instructions()

    if len(message_ids) > 1:
        print(f"[DONE] 메시지 {len(message_ids)}개 처리 완료 표시: {', '.join(map(str, message_ids))}")
    else:
        print(f"[DONE] 메시지 {message_ids[0]} 처리 완료 표시")


def load_memory():
    """기존 메모리 파일 전부 읽기 (tasks/*/task_info.txt)"""
    if not os.path.exists(TASKS_DIR):
        return []

    memories = []

    for task_folder in os.listdir(TASKS_DIR):
        if task_folder.startswith("msg_"):
            task_dir = os.path.join(TASKS_DIR, task_folder)
            task_info_file = os.path.join(task_dir, "task_info.txt")

            if os.path.exists(task_info_file):
                try:
                    message_id = int(task_folder.split("_")[1])
                    with open(task_info_file, "r", encoding="utf-8") as f:
                        content = f.read()
                        memories.append({
                            "message_id": message_id,
                            "task_dir": task_dir,
                            "content": content
                        })
                except Exception as e:
                    print(f"[WARN] {task_folder}/task_info.txt 읽기 오류: {e}")

    memories.sort(key=lambda x: x["message_id"], reverse=True)
    return memories


def poll_new_messages():
    """대기 루프용 — 로컬 파일만 읽어 미처리 메시지 반환.
    Telegram API 호출하지 않음 (listener가 담당).
    working.json 체크 안 함 (대기 중이므로).
    """
    data = load_telegram_messages()
    unprocessed = [
        msg for msg in data.get("messages", [])
        if msg.get("type") == "user" and not msg.get("processed", False)
    ]
    return unprocessed


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


def load_session_memory():
    """세션 시작 시 — session_memory.md 내용 반환."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return None
    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            print(f"[MEMORY] 세션 메모리 로드 완료 ({len(content)} chars)")
            return content
        return None
    except Exception as e:
        print(f"[WARN] session_memory.md 읽기 오류: {e}")
        return None


def _summarize_trimmed_conversations(trimmed_lines):
    """삭제되는 대화 항목들에서 핵심 이벤트/톤을 한 줄 요약으로 추출한다.
    AI 호출 없이 규칙 기반으로 처리 (토큰 비용 0)."""
    if not trimmed_lines:
        return None

    # 키워드 기반 이벤트 추출
    events = []
    tone_signals = {"긍정": 0, "부정": 0, "작업": 0}

    for line in trimmed_lines:
        text = line.strip().lstrip("- ")
        # 주요 이벤트 키워드
        if any(k in text for k in ["성공", "완료", "게시"]):
            tone_signals["긍정"] += 1
        if any(k in text for k in ["실패", "실수", "오류", "버그", "중단"]):
            tone_signals["부정"] += 1
        if any(k in text for k in ["작업", "수정", "구현", "시작", "진행"]):
            tone_signals["작업"] += 1
        # 🤖 또는 👤 이벤트 추출 (핵심 동작만)
        if "🤖" in text:
            # 동사 기반 핵심 추출
            for keyword in ["게시 성공", "답글", "수정", "전송", "브리핑", "분석", "저장", "완료"]:
                if keyword in text:
                    short = text.split("🤖")[1].strip()[:40]
                    events.append(short)
                    break
        elif "👤" in text:
            for keyword in ["해줘", "올려", "달아", "보여", "써", "뽑아", "찾아"]:
                if keyword in text:
                    short = text.split("👤")[1].strip()[:30]
                    events.append(short)
                    break

    if not events:
        return None

    # 톤 결정
    dominant = max(tone_signals, key=tone_signals.get)
    tone_map = {"긍정": "✅순조", "부정": "⚠️이슈있음", "작업": "🔧작업중심"}
    tone = tone_map.get(dominant, "")

    # 최대 3개 이벤트 + 톤
    summary_events = events[:3]
    summary = f"  → [{tone}] " + " / ".join(summary_events)
    return summary


def compact_session_memory():
    """session_memory.md의 '최근 대화' 섹션이 50개를 초과하면 오래된 것부터 삭제.
    삭제되는 대화의 핵심을 한 줄 요약으로 남겨 맥락 유지."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[WARN] session_memory.md 읽기 오류: {e}")
        return

    lines = content.split("\n")

    # '최근 대화' 섹션 찾기
    conv_start = None
    conv_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## 최근 대화"):
            conv_start = i + 1
        elif conv_start is not None and line.strip().startswith("## "):
            conv_end = i
            break

    if conv_start is None:
        return

    if conv_end is None:
        conv_end = len(lines)

    # 대화 항목 추출 (- 로 시작하는 줄)
    conv_lines = [l for l in lines[conv_start:conv_end] if l.strip().startswith("- ")]
    other_lines = [l for l in lines[conv_start:conv_end] if not l.strip().startswith("- ") and l.strip()]

    if len(conv_lines) <= SESSION_MEMORY_MAX_CONVERSATIONS:
        return  # 정리 불필요

    # 오래된 것 삭제 (앞에서부터)
    trimmed = len(conv_lines) - SESSION_MEMORY_MAX_CONVERSATIONS
    trimmed_lines = conv_lines[:trimmed]
    conv_lines = conv_lines[trimmed:]
    print(f"[COMPACT] 세션 메모리 정리: {trimmed}개 오래된 대화 삭제")

    # 삭제되는 대화의 톤/감정 메모 생성
    summary = _summarize_trimmed_conversations(trimmed_lines)
    if summary:
        # 기존 요약 메모(→로 시작) 위에 새 요약 추가
        conv_lines = [summary] + conv_lines
        print(f"[COMPACT] 톤/이벤트 메모 추가: {summary.strip()}")

    # 재조립
    new_section = other_lines + conv_lines
    new_lines = lines[:conv_start] + new_section + lines[conv_end:]
    new_content = "\n".join(new_lines)

    with open(SESSION_MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


def save_session_summary():
    """세션 종료/크래시 대비 — permanent_memory.md에 '오늘의 핵심 3줄' 기록.
    session_memory.md에서 핵심 이벤트를 추출하여 날짜별로 기록한다.
    이미 오늘 날짜 기록이 있으면 덮어쓴다."""
    import datetime
    today = datetime.date.today().strftime("%m/%d")

    # session_memory 읽기
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            session_content = f.read()
    except Exception:
        return

    # 최근 대화에서 핵심 이벤트 3개 추출
    events = []
    for line in session_content.split("\n"):
        text = line.strip()
        if not text.startswith("- "):
            continue
        # 중요한 이벤트만 추출
        for keyword in ["성공", "완료", "승인", "수정", "구현", "실패", "결정", "확정", "저장", "게시"]:
            if keyword in text:
                # 타임스탬프 제거하고 핵심만
                clean = text.lstrip("- ").strip()
                # 🤖/👤 이후 텍스트만
                for marker in ["🤖 ", "👤 "]:
                    if marker in clean:
                        clean = clean.split(marker, 1)[1]
                        break
                if len(clean) > 60:
                    clean = clean[:60] + "..."
                events.append(clean)
                break

    if not events:
        return

    # 최대 3줄
    summary_lines = events[-3:]  # 가장 최근 3개

    # permanent_memory.md 읽기
    perm_file = os.path.join(DATA_DIR, "permanent_memory.md")
    if not os.path.exists(perm_file):
        return

    try:
        with open(perm_file, "r", encoding="utf-8") as f:
            perm_content = f.read()
    except Exception:
        return

    # '세션 핵심 로그' 섹션 찾기/만들기
    section_header = "## 세션 핵심 로그"
    summary_text = f"- [{today}] " + " | ".join(summary_lines)

    if section_header in perm_content:
        # 기존 섹션에 추가 (같은 날짜면 교체)
        lines = perm_content.split("\n")
        section_idx = None
        next_section_idx = None
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                section_idx = i
            elif section_idx is not None and i > section_idx and line.strip().startswith("## "):
                next_section_idx = i
                break

        if section_idx is not None:
            if next_section_idx is None:
                next_section_idx = len(lines)

            # 같은 날짜 엔트리 제거
            section_lines = []
            for line in lines[section_idx + 1:next_section_idx]:
                if line.strip().startswith(f"- [{today}]"):
                    continue  # 같은 날짜 교체
                section_lines.append(line)

            # 새 엔트리 추가 (최대 7일치 유지)
            entry_lines = [l for l in section_lines if l.strip().startswith("- [")]
            if len(entry_lines) >= 7:
                # 가장 오래된 것 제거
                for j, l in enumerate(section_lines):
                    if l.strip().startswith("- ["):
                        section_lines.pop(j)
                        break

            section_lines.append(summary_text)

            new_lines = lines[:section_idx + 1] + section_lines + lines[next_section_idx:]
            perm_content = "\n".join(new_lines)
    else:
        # 새 섹션 추가 (파일 끝)
        perm_content = perm_content.rstrip() + f"\n\n{section_header}\n{summary_text}\n"

    try:
        with open(perm_file, "w", encoding="utf-8") as f:
            f.write(perm_content)
        print(f"[SUMMARY] permanent_memory에 오늘의 핵심 3줄 기록 완료")
    except Exception as e:
        print(f"[WARN] permanent_memory 기록 실패: {e}")


# 테스트 코드
if __name__ == "__main__":
    print("=" * 60)
    print("heysquid - 대기 중인 명령 확인")
    print("=" * 60)

    pending = check_telegram()

    if not pending:
        print("\n[OK] 대기 중인 명령이 없습니다. 임무 완료!")
    else:
        print(f"\n[PENDING] 대기 중인 명령: {len(pending)}개\n")

        for i, task in enumerate(pending, 1):
            print(f"--- 명령 #{i} ---")
            print(f"메시지 ID: {task['message_id']}")
            print(f"사용자: {task['user_name']}")
            print(f"시각: {task['timestamp']}")
            print(f"명령: {task['instruction']}")
            if task.get('workspace'):
                print(f"워크스페이스: {task['workspace']}")
            print(f"\n[참고사항 - 최근 24시간 대화]")
            print(task['context_24h'])
            print()
