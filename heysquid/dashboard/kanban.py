"""
heysquid.dashboard.kanban — Kanban board state management.

Manages kanban task cards in data/agent_status.json under the 'kanban' key.
Read-only view on dashboard; tasks created/moved by PM lifecycle hooks.
"""

import json
import os
import time
import random
from datetime import datetime, timedelta

from . import _load_status, _save_status
from ..core.config import DATA_DIR_STR as DATA_DIR

ARCHIVE_FILE = os.path.join(DATA_DIR, "kanban_archive.json")

# Column constants
COL_AUTOMATION = "automation"
COL_TODO = "todo"
COL_IN_PROGRESS = "in_progress"
COL_WAITING = "waiting"
COL_DONE = "done"

VALID_COLUMNS = {COL_AUTOMATION, COL_TODO, COL_IN_PROGRESS, COL_WAITING, COL_DONE}
MAX_DONE_TASKS = 50


def _generate_id():
    """Generate unique kanban task ID."""
    ts = int(time.time())
    rand = random.randint(100, 999)
    return f"kb-{ts}-{rand}"


def _ensure_kanban(data):
    """Ensure kanban section exists in status data."""
    if "kanban" not in data:
        data["kanban"] = {"tasks": []}
    if "tasks" not in data["kanban"]:
        data["kanban"]["tasks"] = []
    return data["kanban"]


def _prune_done_tasks(kanban):
    """Remove oldest Done tasks if over MAX_DONE_TASKS."""
    done = [t for t in kanban["tasks"] if t["column"] == COL_DONE]
    if len(done) <= MAX_DONE_TASKS:
        return
    done_sorted = sorted(done, key=lambda t: t.get("updated_at", ""))
    to_remove = len(done) - MAX_DONE_TASKS
    remove_ids = {t["id"] for t in done_sorted[:to_remove]}
    kanban["tasks"] = [t for t in kanban["tasks"] if t["id"] not in remove_ids]


def add_kanban_task(title, column=COL_TODO, source_message_ids=None,
                    chat_id=None, tags=None):
    """Create a new kanban card.

    Dedup: skips if any source_message_id already exists in a non-done task.
    Returns the task dict or None if skipped.
    """
    if column not in VALID_COLUMNS:
        column = COL_TODO

    data = _load_status()
    kanban = _ensure_kanban(data)

    # Dedup by message_ids
    if source_message_ids:
        existing_msg_ids = set()
        for t in kanban["tasks"]:
            if t["column"] != COL_DONE:
                existing_msg_ids.update(t.get("source_message_ids") or [])
        if any(mid in existing_msg_ids for mid in source_message_ids):
            return None

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task = {
        "id": _generate_id(),
        "title": title[:100],
        "column": column,
        "tags": tags or [],
        "source_message_ids": source_message_ids or [],
        "chat_id": chat_id,
        "created_at": now,
        "updated_at": now,
        "activity_log": [
            {"time": datetime.now().strftime("%H:%M:%S"), "agent": "pm", "message": "Task created"}
        ],
        "result": None,
    }

    kanban["tasks"].append(task)
    _save_status(data)
    return task


def update_kanban_by_message_ids(message_ids, new_column, result=None):
    """Find kanban card(s) by source_message_ids and move to new_column.

    Returns list of updated task IDs.
    """
    if not message_ids or new_column not in VALID_COLUMNS:
        return []

    msg_set = set(message_ids) if isinstance(message_ids, list) else {message_ids}

    data = _load_status()
    kanban = _ensure_kanban(data)

    updated = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for task in kanban["tasks"]:
        task_msgs = set(task.get("source_message_ids") or [])
        if task_msgs & msg_set:
            task["column"] = new_column
            task["updated_at"] = now
            if result is not None:
                task["result"] = result
            task["activity_log"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "pm",
                "message": f"Moved to {new_column}",
            })
            updated.append(task["id"])

    if updated:
        if new_column == COL_DONE:
            _prune_done_tasks(kanban)
        _save_status(data)

    return updated


def add_kanban_activity(task_id, agent, message):
    """Append an activity log entry to a kanban task."""
    data = _load_status()
    kanban = _ensure_kanban(data)

    for task in kanban["tasks"]:
        if task["id"] == task_id:
            task["activity_log"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": agent,
                "message": message,
            })
            task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _save_status(data)
            return True

    return False


def delete_kanban_task(task_id):
    """Delete a kanban card by ID. Returns True if found and deleted."""
    data = _load_status()
    kanban = _ensure_kanban(data)

    original_len = len(kanban["tasks"])
    kanban["tasks"] = [t for t in kanban["tasks"] if t["id"] != task_id]

    if len(kanban["tasks"]) < original_len:
        _save_status(data)
        return True
    return False


def move_kanban_task(task_id, new_column):
    """Move a kanban card to a new column by ID. Records in activity_log."""
    if new_column not in VALID_COLUMNS:
        return False

    data = _load_status()
    kanban = _ensure_kanban(data)

    for task in kanban["tasks"]:
        if task["id"] == task_id:
            old_column = task["column"]
            if old_column == new_column:
                return True  # already there
            task["column"] = new_column
            task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task["activity_log"].append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "agent": "pm",
                "message": f"Moved from {old_column} to {new_column}",
            })
            if new_column == COL_DONE:
                _prune_done_tasks(kanban)
            _save_status(data)
            return True

    return False


# --- Archive ---

def _load_archive():
    """Load kanban archive JSON."""
    try:
        with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_archive(archive):
    """Save kanban archive JSON."""
    with open(ARCHIVE_FILE, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def archive_done_tasks(hours=24):
    """Archive Done tasks older than `hours`.

    Called by daily briefing. Moves old Done tasks from
    agent_status.json → kanban_archive.json.

    Returns list of archived task summaries for briefing report.
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    data = _load_status()
    kanban = _ensure_kanban(data)

    to_archive = []
    to_keep = []

    for task in kanban["tasks"]:
        if task["column"] == COL_DONE and task.get("updated_at", "") < cutoff_str:
            task["archived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            to_archive.append(task)
        else:
            to_keep.append(task)

    if not to_archive:
        return []

    # Save to archive file
    archive = _load_archive()
    archive.extend(to_archive)
    # Keep max 200 archived tasks
    if len(archive) > 200:
        archive = archive[-200:]
    _save_archive(archive)

    # Remove from active kanban
    kanban["tasks"] = to_keep
    _save_status(data)

    # Return summaries for briefing
    return [
        {"id": t["id"], "title": t["title"], "done_at": t.get("updated_at", "")}
        for t in to_archive
    ]


def get_archive(limit=50):
    """Get archived tasks (newest first)."""
    archive = _load_archive()
    return list(reversed(archive))[:limit]
