"""
heysquid.core.hub — PM hub.

Facade module: re-exports all public API from domain sub-modules.
Central hub for the PM — message reception, aggregation, context building,
and channel broadcasting all go through here. (check_telegram, combine_tasks,
poll_new_messages, reply_telegram, reply_broadcast, report_broadcast,
get_24h_context, _detect_workspace)

Key features:
- check_telegram() - Check for new commands (includes last 48h conversation history)
- reply_broadcast() / reply_telegram() - PM response broadcast
- report_broadcast() - Task completion report broadcast
- report_telegram() - Send results and save to memory
- mark_done_telegram() - Mark as processed
- load_memory() - Load existing memory
- reserve_memory_telegram() - Reserve memory at task start
+ workspace integration (switch_workspace on project mention)
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
    """PM response — broadcast to all channels.

    Marks as processed if at least one channel send succeeds.

    Args:
        chat_id: Original chat ID
        message_id: Target message ID (int or list)
        text: Response text
    Returns:
        bool: True if at least one send succeeded
    """
    ids = message_id if isinstance(message_id, list) else [message_id]
    ids_set = set(ids)

    # 1. Send to all channels
    results = broadcast_all(text)
    success = any(results.values()) if results else False

    # If no channels are registered (e.g., testing), try direct Telegram send
    if not results:
        try:
            from ..channels.telegram import send_message_sync
            success = send_message_sync(chat_id, text, _save=False)
        except Exception:
            success = False

    # 2. Mark as processed + save bot response only on successful send
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
    """Task completion report — broadcast to all channels."""
    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    message = result_text
    if files:
        file_names = [os.path.basename(f) for f in files]
        message += f"\n\n[FILE] {', '.join(file_names)}"

    if len(message_ids) > 1:
        message += f"\n\n_{len(message_ids)} messages processed together_"

    print(f"\n[SEND] Broadcasting results to all channels...")
    _dashboard_log('pm', 'Mission complete — broadcasting report')

    # Text report -> all channels
    results = broadcast_all(message)
    success = any(results.values()) if results else False

    # Direct Telegram send if no channels registered
    if not results:
        try:
            from ..channels.telegram import send_files_sync
            success = send_files_sync(chat_id, message, files or [])
        except Exception:
            success = False
    else:
        # If files exist -> broadcast to all channels
        if files and success:
            broadcast_files(files)

    if success:
        print("[OK] Results sent successfully!")
        save_bot_response(
            chat_id=chat_id,
            text=message,
            reply_to_message_ids=message_ids,
            files=[os.path.basename(f) for f in (files or [])],
            channel="broadcast"
        )
    else:
        print("[ERROR] Failed to send results!")

    return success


def reply_telegram(chat_id, message_id, text):
    """Natural conversation response — backward-compatible wrapper for reply_broadcast()."""
    return reply_broadcast(chat_id, message_id, text)


# ============================================================
# Orchestration functions
# ============================================================


def get_24h_context(messages, current_message_id):
    """Generate last 48 hours of conversation history"""
    now = datetime.now()
    cutoff_time = now - timedelta(hours=48)

    context_lines = ["=== Last 48 Hours Conversation History ===\n"]

    for msg in messages:
        if msg.get("type") == "user" and msg["message_id"] == current_message_id:
            break

        # Exclude relay/broadcast messages from context (prevent duplicates)
        if msg.get("channel") == "broadcast":
            continue

        msg_time = datetime.strptime(msg["timestamp"], "%Y-%m-%d %H:%M:%S")
        if msg_time < cutoff_time:
            continue

        msg_type = msg.get("type", "user")

        if msg_type == "user":
            user_name = msg.get("first_name", "User")
            text = msg.get("text", "")
            files = msg.get("files", [])
            file_info = f" [Attached: {len(files)} file(s)]" if files else ""
            location = msg.get("location")
            location_info = f" [Location: {location['latitude']}, {location['longitude']}]" if location else ""
            context_lines.append(f"[{msg['timestamp']}] {user_name}: {text}{file_info}{location_info}")

        elif msg_type == "bot":
            text = msg.get("text", "")
            text_preview = text[:150] + "..." if len(text) > 150 else text
            files = msg.get("files", [])
            file_names = [f.get("name", str(f)) if isinstance(f, dict) else str(f) for f in files]
            file_info = f" [Sent: {', '.join(file_names)}]" if files else ""
            context_lines.append(f"[{msg['timestamp']}] heysquid: {text_preview}{file_info}")

    if len(context_lines) == 1:
        return "No conversation history within the last 48 hours."

    return "\n".join(context_lines)


def _detect_workspace(instruction):
    """
    Detect workspace project name from instruction text.

    Returns:
        str or None: Detected workspace name
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
    Check for new Telegram commands.

    Returns:
        list: List of pending instructions
    """
    lock_info = check_working_lock()

    if lock_info:
        if lock_info.get("stale"):
            print("[RESTART] Resuming stale task")

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
                    "**Previous task was interrupted**\n\n"
                    f"Instruction: {lock_info.get('instruction_summary')}...\n"
                    f"Started at: {lock_info.get('started_at')}\n"
                    f"Last activity: {lock_info.get('last_activity')}\n\n"
                    "Restarting from the beginning."
                )
                send_message_sync(chat_id, alert_msg, _save=False)
                save_bot_response(chat_id, alert_msg, message_ids, channel="system")

            try:
                os.remove(WORKING_LOCK_FILE)
                print("[UNLOCK] Stale lock removed")
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

        print(f"[WARN] Another task is in progress: message_id={lock_info.get('message_id')}")
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

        # Workspace detection
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
        # Mark returned messages as "seen" immediately — structural duplicate prevention
        # Regardless of which function PM AI uses, seen=True messages are skipped by poll_new_messages()
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
    """Combine multiple unprocessed messages into a single unified task"""
    if not pending_tasks:
        return None

    sorted_tasks = sorted(pending_tasks, key=lambda x: x['timestamp'])
    is_stale_resume = any(task.get('stale_resume', False) for task in sorted_tasks)

    combined_parts = []

    if is_stale_resume:
        combined_parts.append("[Resuming interrupted task]")
        combined_parts.append("Check the progress of the previous task, then proceed rationally.")
        combined_parts.append("Review previous work artifacts in the tasks/ folder and continue if possible,")
        combined_parts.append("but restart from scratch if that would be safer.")
        combined_parts.append("")
        combined_parts.append("---")
        combined_parts.append("")

    all_files = []

    # Workspace detection (use first detected)
    detected_workspace = None
    for task in sorted_tasks:
        if task.get("workspace"):
            detected_workspace = task["workspace"]
            break

    # Add workspace info
    if detected_workspace:
        try:
            from .workspace import get_workspace, switch_workspace
            ws_info = get_workspace(detected_workspace)
            if ws_info:
                context_md = switch_workspace(detected_workspace)
                combined_parts.append(f"[Active workspace: {detected_workspace}]")
                combined_parts.append(f"Project path: {ws_info['path']}")
                combined_parts.append(f"Description: {ws_info.get('description', '')}")
                if context_md:
                    combined_parts.append(f"\n--- Project Context ---\n{context_md}\n---\n")
                combined_parts.append("")
        except Exception:
            pass

    for i, task in enumerate(sorted_tasks, 1):
        combined_parts.append(f"[Request {i}] ({task['timestamp']})")

        if task['instruction']:
            combined_parts.append(task['instruction'])

        files = task.get('files', [])
        if files:
            combined_parts.append("")
            combined_parts.append("Attached files:")
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
                combined_parts.append(f"     Path: {file_path}")

                all_files.append(file_info)

        location = task.get('location')
        if location:
            combined_parts.append("")
            combined_parts.append("Location info:")
            combined_parts.append(f"  Latitude: {location['latitude']}")
            combined_parts.append(f"  Longitude: {location['longitude']}")
            if 'accuracy' in location:
                combined_parts.append(f"  Accuracy: +/-{location['accuracy']}m")
            maps_url = f"https://www.google.com/maps?q={location['latitude']},{location['longitude']}"
            combined_parts.append(f"  Google Maps: {maps_url}")

        combined_parts.append("")

    combined_instruction = "\n".join(combined_parts).strip()

    context_24h = sorted_tasks[0]['context_24h']
    if context_24h and context_24h != "No conversation history within the last 48 hours.":
        combined_instruction = combined_instruction + "\n\n---\n\n[Reference]\n" + context_24h

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
    """Pick one task. Prioritize replies to WAITING cards, then oldest TODO.

    Returns:
        dict: {task, waiting_card, remaining} or None
    """
    if not pending_tasks:
        return None

    # Phase 1: WAITING card reply matching
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

            # Fallback: 1 WAITING + 1 pending -> auto-match (trivially obvious)
            if len(waiting_cards) == 1 and len(pending_tasks) == 1:
                return {"task": pending_tasks[0], "waiting_card": waiting_cards[0], "remaining": []}
    except Exception as e:
        print(f"[WARN] WAITING matching failed: {e}")

    # Phase 2: oldest TODO
    sorted_tasks = sorted(pending_tasks, key=lambda x: x['timestamp'])
    return {"task": sorted_tasks[0], "waiting_card": None, "remaining": sorted_tasks[1:]}


def suggest_card_merge(chat_id):
    """Return merge suggestion text if there are multiple active cards for the same chat_id.

    Returns:
        dict or None: {
            "text": Suggestion message to send to the user,
            "cards": Card list,
            "target_id": Oldest card ID,
            "source_ids": Remaining card IDs,
        }
    """
    from ..dashboard.kanban import get_mergeable_cards
    cards = get_mergeable_cards(chat_id)
    if len(cards) < 2:
        return None

    target = cards[0]  # oldest
    sources = cards[1:]

    lines = [f"There are {len(cards)} active cards on the kanban. Merge into one?"]
    for i, c in enumerate(cards):
        col = c["column"][:4].upper()
        title = c.get("title", "")[:40]
        marker = " <- merge target" if i == 0 else ""
        lines.append(f"  {i+1}. [{col}] {title}{marker}")
    lines.append("")
    lines.append('"Yes" -> merge all / "No" -> proceed as is')

    return {
        "text": "\n".join(lines),
        "cards": cards,
        "target_id": target["id"],
        "source_ids": [c["id"] for c in sources],
    }


def check_remaining_cards():
    """Check remaining cards before sleep. Return suggestion text if active cards exist.

    Returns:
        dict or None: {
            "text": Message to send to the user,
            "cards": {"todo": [...], "in_progress": [...], "waiting": [...]},
            "card_ids": [Full card ID list],
        }
    """
    from ..dashboard.kanban import get_all_active_cards
    cards = get_all_active_cards()

    total = sum(len(v) for v in cards.values())
    if total == 0:
        return None

    lines = [f"Before entering standby — {total} card(s) remaining on kanban:"]
    for col, label in [("in_progress", "In Progress"), ("todo", "Todo"), ("waiting", "Waiting")]:
        for c in cards[col]:
            title = c.get("title", "")[:40]
            lines.append(f"  {label} | {title}")
    lines.append("")
    lines.append("What should we do?")
    lines.append("1) Clear all (mark as Done)")
    lines.append("2) Start working now")
    lines.append("3) Just standby (later)")

    all_ids = []
    for col_cards in cards.values():
        all_ids.extend(c["id"] for c in col_cards)

    return {
        "text": "\n".join(lines),
        "cards": cards,
        "card_ids": all_ids,
    }


def ask_and_wait(chat_id, message_id, text):
    """PM sends a question + kanban IN_PROGRESS->WAITING + release working lock.

    Unlike reply_broadcast, does NOT set processed=True (task not yet complete).
    """
    ids = message_id if isinstance(message_id, list) else [message_id]

    # 1. Send (capture sent_message_id)
    from ..channels.telegram import send_message_sync
    result = send_message_sync(chat_id, text, _save=False)
    sent_message_id = result if isinstance(result, int) else None

    if not result:
        return False

    # 2. Save bot response
    save_bot_response(chat_id, text, ids, channel="broadcast",
                      sent_message_id=sent_message_id)

    # 3. Kanban: transition to WAITING
    try:
        from ..dashboard.kanban import set_task_waiting, get_active_kanban_task_id
        task_id = get_active_kanban_task_id()
        if task_id:
            sent_ids = [sent_message_id] if sent_message_id else []
            set_task_waiting(task_id, sent_ids, reason=f"Waiting: {text[:50]}")
    except Exception:
        pass

    # 4. Release working lock (allow processing other TODOs)
    remove_working_lock(transition_to_waiting=True)
    return True


def poll_new_messages():
    """For the standby loop — reads only local files to return unprocessed messages.
    Does not call Telegram API (listener handles that).
    Does not check working.json (since we're in standby).
    """
    data = load_telegram_messages()
    unprocessed = [
        msg for msg in data.get("messages", [])
        if msg.get("type") == "user"
        and not msg.get("processed", False)
        and not msg.get("seen", False)  # Skip seen messages (prevent duplicates)
    ]
    return unprocessed


def check_due_posts():
    """Check scheduled thread posts.

    Returns posts from threads_schedule.json where scheduled_time has passed
    and status is "scheduled".

    Returns:
        list[dict]: Posts due for publishing (empty list if none)
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
    """Change scheduled thread post status to 'posted'."""
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


# Test code
if __name__ == "__main__":
    print("=" * 60)
    print("heysquid - Check pending commands")
    print("=" * 60)

    pending = check_telegram()

    if not pending:
        print("\n[OK] No pending commands. All done!")
    else:
        print(f"\n[PENDING] Pending commands: {len(pending)}\n")

        for i, task in enumerate(pending, 1):
            print(f"--- Command #{i} ---")
            print(f"Message ID: {task['message_id']}")
            print(f"User: {task['user_name']}")
            print(f"Time: {task['timestamp']}")
            print(f"Command: {task['instruction']}")
            if task.get('workspace'):
                print(f"Workspace: {task['workspace']}")
            print(f"\n[Reference - Last 48h Conversation]")
            print(task['context_24h'])
            print()
