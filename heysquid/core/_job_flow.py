"""
heysquid.core._job_flow — job lifecycle (reserve / report / mark_done).

Functions:
- reserve_memory_telegram
- report_telegram
- mark_done_telegram
- _format_file_size
"""

import os
from datetime import datetime

from ..channels._msg_store import load_telegram_messages, save_telegram_messages, load_and_modify, save_bot_response
from ._working_lock import _dashboard_log, load_new_instructions, clear_new_instructions
from ..memory.tasks import get_task_dir, update_index
from ..channels.telegram import send_files_sync, run_async_safe


def _format_file_size(size_bytes):
    """Convert file size to human-readable format"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / 1024 / 1024:.1f} MB"


def reserve_memory_telegram(instruction, chat_id, timestamp, message_id):
    """Reserve memory immediately at task start"""
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
        msg_id_info = f"{', '.join(map(str, message_ids))} (combined {len(message_ids)} messages)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[Time] {now.strftime("%Y-%m-%d %H:%M:%S")}
[MessageID] {msg_id_info}
[Source] Telegram (chat_id: {chat_id})
[MessageDate]
{msg_date_info}
[Instruction] {instruction}
[Result] (task in progress...)
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    update_index(
        message_id=main_message_id,
        instruction=instruction,
        result_summary="(task in progress...)",
        files=[],
        chat_id=chat_id,
        timestamp=timestamps[0]
    )

    for i, (msg_id, ts) in enumerate(zip(message_ids[1:], timestamps[1:]), 2):
        ref_dir = get_task_dir(msg_id)
        ref_file = os.path.join(ref_dir, "task_info.txt")
        ref_content = f"""[Time] {now.strftime("%Y-%m-%d %H:%M:%S")}
[MessageID] {msg_id}
[Source] Telegram (chat_id: {chat_id})
[MessageDate] {ts}
[Instruction] (combined into main task msg_{main_message_id})
[Reference] tasks/msg_{main_message_id}/
[Result] (task in progress...)
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(combined into msg_{main_message_id})",
            result_summary="(task in progress...)",
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] Memory reserved: {task_dir}/task_info.txt")
    if len(message_ids) > 1:
        print(f"   Combined messages: {len(message_ids)} ({', '.join(map(str, message_ids))})")


def report_telegram(instruction, result_text, chat_id, timestamp, message_id, files=None):
    """Broadcast task results to all channels and save to memory"""
    if isinstance(message_id, list):
        message_ids = message_id
        main_message_id = message_ids[0]
        timestamps = timestamp if isinstance(timestamp, list) else [timestamp] * len(message_ids)
    else:
        message_ids = [message_id]
        main_message_id = message_id
        timestamps = [timestamp]

    # Broadcast to all channels (delegated to hub)
    from .hub import report_broadcast
    success = report_broadcast(instruction, result_text, chat_id, timestamp, message_id, files)

    if not success:
        result_text = f"[Send failed] {result_text}"
        files = []

    task_dir = get_task_dir(main_message_id)
    filepath = os.path.join(task_dir, "task_info.txt")

    now = datetime.now()

    if len(message_ids) > 1:
        msg_id_info = f"{', '.join(map(str, message_ids))} (combined {len(message_ids)} messages)"
        msg_date_info = "\n".join([f"  - msg_{mid}: {ts}" for mid, ts in zip(message_ids, timestamps)])
    else:
        msg_id_info = str(main_message_id)
        msg_date_info = timestamps[0]

    content = f"""[Time] {now.strftime("%Y-%m-%d %H:%M:%S")}
[MessageID] {msg_id_info}
[Source] Telegram (chat_id: {chat_id})
[MessageDate]
{msg_date_info}
[Instruction] {instruction}
[Result] {result_text}
"""

    if files:
        file_names = [os.path.basename(f) for f in files]
        content += f"[SentFiles] {', '.join(file_names)}\n"

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
        ref_content = f"""[Time] {now.strftime("%Y-%m-%d %H:%M:%S")}
[MessageID] {msg_id}
[Source] Telegram (chat_id: {chat_id})
[MessageDate] {ts}
[Instruction] (combined into main task msg_{main_message_id})
[Reference] tasks/msg_{main_message_id}/
[Result] {result_text[:100]}...
"""
        with open(ref_file, "w", encoding="utf-8") as f:
            f.write(ref_content)

        update_index(
            message_id=msg_id,
            instruction=f"(combined into msg_{main_message_id})",
            result_summary=result_text[:100],
            files=[],
            chat_id=chat_id,
            timestamp=ts
        )

    print(f"[MEM] Memory saved: {task_dir}/task_info.txt")

    # Kanban: move to Done
    try:
        from ..dashboard.kanban import update_kanban_by_message_ids, COL_DONE
        update_kanban_by_message_ids(message_ids, COL_DONE, result=result_text[:200])
    except Exception:
        pass


def _set_done_reactions(message_ids):
    """Set ✅ reaction on processed messages (best-effort)."""
    try:
        from telegram import ReactionTypeEmoji
        from ..channels.telegram import _get_bot

        data = load_telegram_messages()
        bot = _get_bot()

        for msg in data.get("messages", []):
            if msg["message_id"] in message_ids:
                chat_id = msg.get("chat_id")
                if not chat_id:
                    continue
                try:
                    run_async_safe(bot.set_message_reaction(
                        chat_id=chat_id,
                        message_id=msg["message_id"],
                        reaction=[ReactionTypeEmoji(emoji="✅")],
                    ))
                except Exception:
                    pass
    except Exception:
        pass


def mark_done_telegram(message_id):
    """Mark Telegram messages as processed — uses flock"""
    if isinstance(message_id, list):
        message_ids = message_id
    else:
        message_ids = [message_id]

    new_instructions = load_new_instructions()
    if new_instructions:
        print(f"[LOG] Processing {len(new_instructions)} additional instructions added during work")
        for inst in new_instructions:
            message_ids.append(inst["message_id"])

    ids_set = set(message_ids)

    def _mark_done(data):
        for msg in data.get("messages", []):
            if msg["message_id"] in ids_set:
                msg["processed"] = True
        return data

    load_and_modify(_mark_done)
    clear_new_instructions()

    # Set ✅ reaction on completed messages
    _set_done_reactions(ids_set)

    if len(message_ids) > 1:
        print(f"[DONE] Marked {len(message_ids)} messages as processed: {', '.join(map(str, message_ids))}")
    else:
        print(f"[DONE] Marked message {message_ids[0]} as processed")
