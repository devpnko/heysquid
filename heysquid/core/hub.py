"""
heysquid.core.hub — PM 허브.

Facade module: re-exports all public API from domain sub-modules.
PM의 중앙 허브 — 메시지 수신, 조합, 컨텍스트 빌드, 채널 브로드캐스트가
모두 여기를 거쳐간다. (check_telegram, combine_tasks, poll_new_messages,
reply_telegram, reply_broadcast, report_broadcast, get_24h_context,
_detect_workspace)

주요 기능:
- check_telegram() - 새로운 명령 확인 (최근 48시간 대화 내역 포함)
- reply_broadcast() / reply_telegram() - PM 응답 브로드캐스트
- report_broadcast() - 작업 완료 리포트 브로드캐스트
- report_telegram() - 결과 전송 및 메모리 저장
- mark_done_telegram() - 처리 완료 표시
- load_memory() - 기존 메모리 로드
- reserve_memory_telegram() - 작업 시작 시 메모리 예약
+ workspace 연동 (switch_workspace on project mention)
"""

import os
from datetime import datetime, timedelta

from .config import DATA_DIR_STR as DATA_DIR

# --- Re-exports from sub-modules (public API — DO NOT REMOVE) ---

# channels._msg_store
from ..channels._msg_store import (                   # noqa: F401
    load_telegram_messages,
    save_telegram_messages,
    load_and_modify,
    save_bot_response,
    _safe_parse_timestamp,
    _cleanup_old_messages,
    _poll_telegram_once,
)

# core._working_lock
from ._working_lock import (                          # noqa: F401
    _dashboard_log,
    check_working_lock,
    create_working_lock,
    update_working_activity,
    remove_working_lock,
    check_new_messages_during_work,
    save_new_instructions,
    load_new_instructions,
    clear_new_instructions,
)

# memory.tasks
from ..memory.tasks import (                          # noqa: F401
    load_index,
    save_index,
    update_index,
    search_memory,
    get_task_dir,
    load_memory,
)

# memory.session
from ..memory.session import (                        # noqa: F401
    load_session_memory,
    compact_session_memory,
    _summarize_trimmed_conversations,
    save_session_summary,
)

# memory.recovery
from ..memory.recovery import (                       # noqa: F401
    check_crash_recovery,
    check_interrupted,
)

# core._job_flow
from ._job_flow import (                              # noqa: F401
    reserve_memory_telegram,
    report_telegram,
    mark_done_telegram,
    _format_file_size,
)

# channels._router (for broadcast functions below)
from ..channels._router import broadcast_all, broadcast_files  # noqa: F401

# paths (for backwards compat — callers that did `from telegram_bot import MESSAGES_FILE`)
from .paths import (                                  # noqa: F401
    MESSAGES_FILE,
    WORKING_LOCK_FILE,
    NEW_INSTRUCTIONS_FILE,
    INTERRUPTED_FILE,
    SESSION_MEMORY_FILE,
    INDEX_FILE,
    SESSION_MEMORY_MAX_CONVERSATIONS,
    WORKING_LOCK_TIMEOUT,
)


# ============================================================
# Broadcast functions
# ============================================================

def reply_broadcast(chat_id, message_id, text):
    """PM 응답 — 전체 채널 브로드캐스트.

    하나라도 채널 전송 성공이면 processed 마킹.

    Args:
        chat_id: 원본 채팅 ID
        message_id: 응답 대상 메시지 ID (int 또는 list)
        text: 응답 텍스트
    Returns:
        bool: 하나라도 전송 성공이면 True
    """
    ids = message_id if isinstance(message_id, list) else [message_id]
    ids_set = set(ids)

    # 1. 전체 채널에 전송
    results = broadcast_all(text)
    success = any(results.values()) if results else False

    # 채널이 하나도 등록 안 되어있으면 (테스트 등) 텔레그램 직접 전송 시도
    if not results:
        try:
            from ..channels.telegram import send_message_sync
            success = send_message_sync(chat_id, text, _save=False)
        except Exception:
            success = False

    # 2. 전송 성공 시에만 processed 마킹 + 봇 응답 기록
    if success:
        def _mark_processed(data):
            for msg in data.get("messages", []):
                if msg["message_id"] in ids_set:
                    msg["processed"] = True
            return data
        load_and_modify(_mark_processed)

        save_bot_response(chat_id, text, ids, channel="broadcast")

        # Kanban: move TODO cards to DONE (conversation complete)
        try:
            from ..dashboard.kanban import update_kanban_by_message_ids, COL_DONE, COL_TODO
            update_kanban_by_message_ids(ids, COL_DONE, from_column=COL_TODO)
        except Exception:
            pass

    return success


def report_broadcast(instruction, result_text, chat_id, timestamp, message_id, files=None):
    """작업 완료 리포트 — 전체 채널에 브로드캐스트."""
    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    message = result_text
    if files:
        file_names = [os.path.basename(f) for f in files]
        message += f"\n\n[FILE] {', '.join(file_names)}"

    if len(message_ids) > 1:
        message += f"\n\n_{len(message_ids)}개 메시지 합산 처리_"

    print(f"\n[SEND] 전체 채널로 결과 전송 중...")
    _dashboard_log('pm', 'Mission complete — broadcasting report')

    # 텍스트 리포트 → 전체 채널
    results = broadcast_all(message)
    success = any(results.values()) if results else False

    # 채널 미등록 시 텔레그램 직접 전송
    if not results:
        try:
            from ..channels.telegram import send_files_sync
            success = send_files_sync(chat_id, message, files or [])
        except Exception:
            success = False
    else:
        # 파일 있으면 → 전체 채널
        if files and success:
            broadcast_files(files)

    if success:
        print("[OK] 결과 전송 완료!")
        save_bot_response(
            chat_id=chat_id,
            text=message,
            reply_to_message_ids=message_ids,
            files=[os.path.basename(f) for f in (files or [])],
            channel="broadcast"
        )
    else:
        print("[ERROR] 결과 전송 실패!")

    return success


def reply_telegram(chat_id, message_id, text):
    """자연스러운 대화 응답 — reply_broadcast()의 하위 호환 래퍼."""
    return reply_broadcast(chat_id, message_id, text)


# ============================================================
# Orchestration functions
# ============================================================


def get_24h_context(messages, current_message_id):
    """최근 48시간 대화 내역 생성"""
    now = datetime.now()
    cutoff_time = now - timedelta(hours=48)

    context_lines = ["=== 최근 48시간 대화 내역 ===\n"]

    for msg in messages:
        if msg.get("type") == "user" and msg["message_id"] == current_message_id:
            break

        # 릴레이/브로드캐스트 메시지는 컨텍스트에서 제외 (중복 방지)
        if msg.get("channel") == "broadcast":
            continue

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
            file_names = [f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in files]
            file_info = f" [전송: {', '.join(file_names)}]" if files else ""
            context_lines.append(f"[{msg['timestamp']}] heysquid: {text_preview}{file_info}")

    if len(context_lines) == 1:
        return "최근 48시간 이내 대화 내역이 없습니다."

    return "\n".join(context_lines)


def _detect_workspace(instruction):
    """
    지시사항에서 워크스페이스 프로젝트명 감지

    Returns:
        str or None: 감지된 워크스페이스 이름
    """
    try:
        from .workspace import list_workspaces
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

            from ..channels.telegram import send_message_sync
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
                send_message_sync(chat_id, alert_msg, _save=False)
                save_bot_response(chat_id, alert_msg, message_ids, channel="system")

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
        # 반환하는 메시지를 즉시 "seen" 마킹 — 중복 처리 구조적 방지
        # PM AI가 어떤 함수를 쓰든, seen=True인 메시지는 poll_new_messages()에서 스킵됨
        seen_ids = {task['message_id'] for task in pending}
        def _mark_seen(data):
            for msg in data.get("messages", []):
                if msg["message_id"] in seen_ids:
                    msg["seen"] = True
                    msg["seen_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return data
        load_and_modify(_mark_seen)

        _dashboard_log('pm', f'Message received ({len(pending)} pending)')

        # Kanban: merge into active card or create new Todo card
        try:
            from ..dashboard.kanban import add_kanban_task, append_message_to_active_card, COL_TODO
            for task in pending:
                title = (task.get("instruction") or "New task")[:80]
                chat_id = task.get("chat_id")
                msg_id = task["message_id"]

                merged = append_message_to_active_card(chat_id, msg_id, title)
                if not merged:
                    add_kanban_task(
                        title=title,
                        column=COL_TODO,
                        source_message_ids=[msg_id],
                        chat_id=chat_id,
                        tags=[f"workspace:{task['workspace']}"] if task.get("workspace") else [],
                    )
        except Exception:
            pass

    return pending


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
            from .workspace import get_workspace, switch_workspace
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
    if context_24h and context_24h != "최근 48시간 이내 대화 내역이 없습니다.":
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


def pick_next_task(pending_tasks):
    """1개 작업 선택. WAITING 카드에 대한 답장 우선, 그 다음 oldest TODO.

    Returns:
        dict: {task, waiting_card, remaining} or None
    """
    if not pending_tasks:
        return None

    # Phase 1: WAITING 카드 reply 매칭
    try:
        from ..dashboard._store import store as _dashboard_store

        kanban_data = _dashboard_store.load("kanban")
        waiting_cards = [t for t in kanban_data.get("tasks", []) if t["column"] == "waiting"]

        if waiting_cards:
            all_msgs = load_telegram_messages().get("messages", [])
            # sent_message_id → WAITING card mapping
            waiting_map = {}
            for card in waiting_cards:
                for sid in (card.get("waiting_sent_ids") or []):
                    waiting_map[sid] = card

            for i, task in enumerate(pending_tasks):
                msg = next((m for m in all_msgs if m["message_id"] == task["message_id"]), None)
                if not msg:
                    continue
                reply_to = msg.get("reply_to_message_id")
                if reply_to and reply_to in waiting_map:
                    remaining = pending_tasks[:i] + pending_tasks[i+1:]
                    return {"task": task, "waiting_card": waiting_map[reply_to], "remaining": remaining}

            # Fallback: 1개 WAITING + 1개 pending → auto-match (하나뿐이면 자명)
            if len(waiting_cards) == 1 and len(pending_tasks) == 1:
                return {"task": pending_tasks[0], "waiting_card": waiting_cards[0], "remaining": []}
    except Exception as e:
        print(f"[WARN] WAITING 매칭 실패: {e}")

    # Phase 2: oldest TODO
    sorted_tasks = sorted(pending_tasks, key=lambda x: x['timestamp'])
    return {"task": sorted_tasks[0], "waiting_card": None, "remaining": sorted_tasks[1:]}


def suggest_card_merge(chat_id):
    """같은 chat_id의 활성 카드가 여러 개면 병합 제안 텍스트 반환.

    Returns:
        dict or None: {
            "text": 사용자에게 보낼 제안 메시지,
            "cards": 카드 리스트,
            "target_id": 가장 오래된 카드 ID,
            "source_ids": 나머지 카드 ID 리스트,
        }
    """
    from ..dashboard.kanban import get_mergeable_cards
    cards = get_mergeable_cards(chat_id)
    if len(cards) < 2:
        return None

    target = cards[0]  # oldest
    sources = cards[1:]

    lines = [f"칸반에 활성 카드가 {len(cards)}개 있어. 하나로 합칠까?"]
    for i, c in enumerate(cards):
        col = c["column"][:4].upper()
        title = c.get("title", "")[:40]
        marker = " ← 여기에 합침" if i == 0 else ""
        lines.append(f"  {i+1}. [{col}] {title}{marker}")
    lines.append("")
    lines.append('"응" → 전부 합침 / "아니" → 그냥 진행')

    return {
        "text": "\n".join(lines),
        "cards": cards,
        "target_id": target["id"],
        "source_ids": [c["id"] for c in sources],
    }


def ask_and_wait(chat_id, message_id, text):
    """PM이 질문 전송 + 칸반 IN_PROGRESS→WAITING + working lock 해제.

    reply_broadcast와 달리 processed=True 안 함 (아직 작업 미완료).
    """
    ids = message_id if isinstance(message_id, list) else [message_id]

    # 1. 전송 (sent_message_id 캡처)
    from ..channels.telegram import send_message_sync
    result = send_message_sync(chat_id, text, _save=False)
    sent_message_id = result if isinstance(result, int) else None

    if not result:
        return False

    # 2. 봇 응답 저장
    save_bot_response(chat_id, text, ids, channel="broadcast",
                      sent_message_id=sent_message_id)

    # 3. 칸반: WAITING 전환
    try:
        from ..dashboard.kanban import set_task_waiting, get_active_kanban_task_id
        task_id = get_active_kanban_task_id()
        if task_id:
            sent_ids = [sent_message_id] if sent_message_id else []
            set_task_waiting(task_id, sent_ids, reason=f"Waiting: {text[:50]}")
    except Exception:
        pass

    # 4. working lock 해제 (다른 TODO 처리 가능하게)
    remove_working_lock(transition_to_waiting=True)
    return True


def poll_new_messages():
    """대기 루프용 — 로컬 파일만 읽어 미처리 메시지 반환.
    Telegram API 호출하지 않음 (listener가 담당).
    working.json 체크 안 함 (대기 중이므로).
    """
    data = load_telegram_messages()
    unprocessed = [
        msg for msg in data.get("messages", [])
        if msg.get("type") == "user"
        and not msg.get("processed", False)
        and not msg.get("seen", False)  # seen 메시지 스킵 (중복 방지)
    ]
    return unprocessed


def check_due_posts():
    """스레드 예약 게시 스케줄 확인.

    threads_schedule.json에서 scheduled_time이 지났고
    status가 "scheduled"인 게시물을 반환한다.

    Returns:
        list[dict]: 게시해야 할 포스트 목록 (빈 리스트면 없음)
    """
    import json

    schedule_path = os.path.join(DATA_DIR, "threads_schedule.json")
    if not os.path.exists(schedule_path):
        return []

    try:
        with open(schedule_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []

    now = datetime.now()
    due = []

    for post in data.get("scheduled_posts", []):
        if post.get("status") != "scheduled":
            continue
        try:
            scheduled = datetime.strptime(post["scheduled_time"], "%Y-%m-%d %H:%M")
        except (KeyError, ValueError):
            continue
        if scheduled <= now:
            due.append(post)

    return due


def mark_post_done(post_id):
    """스레드 예약 게시물 상태를 'posted'로 변경."""
    import json

    schedule_path = os.path.join(DATA_DIR, "threads_schedule.json")
    try:
        with open(schedule_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return False

    for post in data.get("scheduled_posts", []):
        if post.get("id") == post_id:
            post["status"] = "posted"
            break
    else:
        return False

    with open(schedule_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return True


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
            print(f"\n[참고사항 - 최근 48시간 대화]")
            print(task['context_24h'])
            print()
