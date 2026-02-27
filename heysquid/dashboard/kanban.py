"""
heysquid.dashboard.kanban — Kanban board state management.

Manages kanban task cards in data/kanban.json (split from agent_status.json).
Read-only view on dashboard; tasks created/moved by PM lifecycle hooks.
"""

import json
import os
import time
import random
from datetime import datetime, timedelta

from ._store import store, SectionConfig, migrate_section_from_status
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


# --- Section registration + one-time migration ---

def _default_kanban():
    return {"tasks": [], "next_short_id": 1}

store.register(SectionConfig("kanban", "kanban.json", _default_kanban))

_cfg = store.get_config("kanban")
migrate_section_from_status("kanban", _cfg.file_path, _cfg.lock_path, _cfg.bak_path)


def _migrate_short_ids():
    """기존 카드에 short_id가 없으면 부여."""
    def _modify(data):
        counter = data.get("next_short_id", 1)
        changed = False
        for t in data.get("tasks", []):
            if "short_id" not in t:
                t["short_id"] = f"K{counter}"
                counter += 1
                changed = True
        if changed:
            data["next_short_id"] = counter
        else:
            return False  # skip save

    store.modify("kanban", _modify)

_migrate_short_ids()


def resolve_card(identifier: str):
    """K-ID(예: 'K3', 'k3')로 카드를 찾아 반환. 없으면 None."""
    sid = identifier.strip().upper()
    if not sid.startswith("K"):
        return None
    data = store.load("kanban")
    for t in data.get("tasks", []):
        if t.get("short_id", "").upper() == sid:
            return t
    return None


def _generate_id():
    """Generate unique kanban task ID."""
    ts = int(time.time())
    rand = random.randint(100, 999)
    return f"kb-{ts}-{rand}"


def _prune_done_tasks(data):
    """Remove oldest Done tasks if over MAX_DONE_TASKS."""
    done = [t for t in data["tasks"] if t["column"] == COL_DONE]
    if len(done) <= MAX_DONE_TASKS:
        return
    done_sorted = sorted(done, key=lambda t: t.get("updated_at", ""))
    to_remove = len(done) - MAX_DONE_TASKS
    remove_ids = {t["id"] for t in done_sorted[:to_remove]}
    data["tasks"] = [t for t in data["tasks"] if t["id"] not in remove_ids]


def add_kanban_task(title, column=COL_TODO, source_message_ids=None,
                    chat_id=None, tags=None):
    """Create a new kanban card.

    Dedup: skips if any source_message_id already exists in a non-done task.
    Returns the task dict or None if skipped.
    """
    if column not in VALID_COLUMNS:
        column = COL_TODO

    result_task = [None]

    def _modify(data):
        tasks = data.setdefault("tasks", [])

        # Dedup by message_ids
        if source_message_ids:
            existing_msg_ids = set()
            for t in tasks:
                if t["column"] != COL_DONE:
                    existing_msg_ids.update(t.get("source_message_ids") or [])
            if any(mid in existing_msg_ids for mid in source_message_ids):
                return False  # skip save

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        short_id_num = data.get("next_short_id", 1)
        task = {
            "id": _generate_id(),
            "short_id": f"K{short_id_num}",
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
        tasks.append(task)
        data["next_short_id"] = short_id_num + 1
        result_task[0] = task

    store.modify("kanban", _modify)
    return result_task[0]


def append_message_to_active_card(chat_id, message_id, text):
    """같은 chat_id의 non-done 카드에 메시지를 병합.

    Returns:
        bool: 병합 성공 여부 (기존 카드가 있으면 True)
    """
    merged = [False]

    def _modify(data):
        candidates = [
            t for t in data.get("tasks", [])
            if t.get("chat_id") == chat_id
            and t["column"] in (COL_IN_PROGRESS, COL_TODO, COL_WAITING)
            and message_id not in (t.get("source_message_ids") or [])
        ]
        if not candidates:
            return False  # skip save

        target = max(candidates, key=lambda t: t.get("updated_at", ""))
        target.setdefault("source_message_ids", []).append(message_id)
        target["title"] = (text or "")[:100]
        target["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        target.setdefault("activity_log", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "agent": "user",
            "message": f"💬 {(text or '')[:60]}",
        })
        merged[0] = True

    store.modify("kanban", _modify)
    return merged[0]


def get_mergeable_cards(chat_id):
    """같은 chat_id의 활성 카드(non-done, non-automation) 목록 반환.

    Returns:
        list[dict]: 카드 리스트 (created_at 오름차순). len < 2면 병합 불필요.
    """
    data = store.load("kanban")
    cards = [
        t for t in data.get("tasks", [])
        if t.get("chat_id") == chat_id
        and t["column"] in (COL_IN_PROGRESS, COL_TODO, COL_WAITING)
    ]
    return sorted(cards, key=lambda t: t.get("created_at", ""))


def get_all_active_cards():
    """모든 활성 카드(non-done, non-automation) 목록을 컬럼별로 반환.

    Returns:
        dict: {"todo": [...], "in_progress": [...], "waiting": [...]}
    """
    data = store.load("kanban")
    result = {"todo": [], "in_progress": [], "waiting": []}
    for t in data.get("tasks", []):
        col = t.get("column")
        if col in result:
            result[col].append(t)
    return result


def merge_kanban_tasks(source_id, target_id):
    """source 카드를 target 카드에 병합 후 source 삭제.

    source의 source_message_ids, activity_log를 target에 합치고,
    source 카드는 삭제한다.

    Returns:
        bool: 병합 성공 여부
    """
    if source_id == target_id:
        return False

    merged = [False]

    def _modify(data):
        tasks = data.get("tasks", [])
        source = next((t for t in tasks if t["id"] == source_id), None)
        target = next((t for t in tasks if t["id"] == target_id), None)
        if not source or not target:
            return False  # skip save

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Merge source_message_ids (dedup)
        existing = set(target.get("source_message_ids") or [])
        for mid in (source.get("source_message_ids") or []):
            if mid not in existing:
                target.setdefault("source_message_ids", []).append(mid)

        # Merge activity_log
        target.setdefault("activity_log", []).append({
            "time": datetime.now().strftime("%H:%M:%S"),
            "agent": "pm",
            "message": f"Merged from [{source['title'][:40]}]",
        })
        for entry in (source.get("activity_log") or []):
            target["activity_log"].append(entry)

        # Merge tags (dedup)
        existing_tags = set(target.get("tags") or [])
        for tag in (source.get("tags") or []):
            if tag not in existing_tags:
                target.setdefault("tags", []).append(tag)

        target["updated_at"] = now

        # Remove source
        data["tasks"] = [t for t in tasks if t["id"] != source_id]
        merged[0] = True

    store.modify("kanban", _modify)
    return merged[0]


def update_kanban_by_message_ids(message_ids, new_column, result=None, from_column=None):
    """Find kanban card(s) by source_message_ids and move to new_column.

    Args:
        from_column: If set, only move tasks currently in this column.

    Returns list of updated task IDs.
    """
    if not message_ids or new_column not in VALID_COLUMNS:
        return []

    msg_set = set(message_ids) if isinstance(message_ids, list) else {message_ids}
    updated = []

    def _modify(data):
        tasks = data.setdefault("tasks", [])
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for task in tasks:
            task_msgs = set(task.get("source_message_ids") or [])
            if task_msgs & msg_set:
                if from_column and task["column"] != from_column:
                    continue
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

        if not updated:
            return False  # skip save
        if new_column == COL_DONE:
            _prune_done_tasks(data)

    store.modify("kanban", _modify)
    return updated


def add_kanban_activity(task_id, agent, message):
    """Append an activity log entry to a kanban task."""
    found = [False]

    def _modify(data):
        for task in data.get("tasks", []):
            if task["id"] == task_id:
                task["activity_log"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "agent": agent,
                    "message": message,
                })
                task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                found[0] = True
                return
        return False  # skip save

    store.modify("kanban", _modify)
    return found[0]


def delete_kanban_task(task_id):
    """Delete a kanban card by ID. Returns True if found and deleted."""
    deleted = [False]

    def _modify(data):
        tasks = data.get("tasks", [])
        original_len = len(tasks)
        data["tasks"] = [t for t in tasks if t["id"] != task_id]
        if len(data["tasks"]) < original_len:
            deleted[0] = True
            return
        return False  # skip save

    store.modify("kanban", _modify)
    return deleted[0]


def move_kanban_task(task_id, new_column):
    """Move a kanban card to a new column by ID. Records in activity_log."""
    if new_column not in VALID_COLUMNS:
        return False

    moved = [False]

    def _modify(data):
        for task in data.get("tasks", []):
            if task["id"] == task_id:
                old_column = task["column"]
                if old_column == new_column:
                    moved[0] = True
                    return False  # already there, skip save
                task["column"] = new_column
                task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                task["activity_log"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "agent": "pm",
                    "message": f"Moved from {old_column} to {new_column}",
                })
                if new_column == COL_DONE:
                    _prune_done_tasks(data)
                moved[0] = True
                return
        return False  # task not found, skip save

    store.modify("kanban", _modify)
    return moved[0]


def get_active_kanban_task_id():
    """Get the kanban task ID for the currently active work (from working.json).

    Finds the IN_PROGRESS or WAITING card matching working.json's message_ids.
    Returns task ID string or None.
    """
    working_file = os.path.join(DATA_DIR, "working.json")
    try:
        with open(working_file, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    msg_id = lock.get("message_id")
    if isinstance(msg_id, list):
        msg_set = set(msg_id)
    else:
        msg_set = {msg_id}

    data = store.load("kanban")
    for task in data.get("tasks", []):
        if task["column"] not in (COL_IN_PROGRESS, COL_WAITING):
            continue
        task_msgs = set(task.get("source_message_ids") or [])
        if task_msgs & msg_set:
            return task["id"]
    return None


def log_agent_activity(agent, message):
    """Log activity to the active kanban card (single flock operation).

    Reads working.json to find message_ids, then finds and updates
    the matching kanban card in a single store.modify() call.
    """
    working_file = os.path.join(DATA_DIR, "working.json")
    try:
        with open(working_file, "r", encoding="utf-8") as f:
            lock = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    msg_id = lock.get("message_id")
    msg_set = set(msg_id) if isinstance(msg_id, list) else {msg_id}

    def _modify(data):
        for task in data.get("tasks", []):
            if task.get("column") not in (COL_IN_PROGRESS, COL_WAITING):
                continue
            task_msgs = set(task.get("source_message_ids") or [])
            if task_msgs & msg_set:
                task.setdefault("activity_log", []).append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "agent": agent,
                    "message": message,
                })
                task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                return
        return False  # no matching task, skip save

    store.modify("kanban", _modify)


def set_active_waiting(reason="Waiting for response"):
    """Move the active kanban card to WAITING column."""
    task_id = get_active_kanban_task_id()
    if task_id:
        move_kanban_task(task_id, COL_WAITING)
        add_kanban_activity(task_id, "pm", reason)


def set_task_waiting(task_id, sent_message_ids, reason="Waiting for response"):
    """IN_PROGRESS → WAITING 전환 + sent_message_ids 저장 (reply 매칭용)."""
    moved = [False]

    def _modify(data):
        for task in data.get("tasks", []):
            if task["id"] == task_id:
                task["column"] = COL_WAITING
                task["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                task["waiting_sent_ids"] = sent_message_ids or []
                task["waiting_since"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                task["activity_log"].append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "agent": "pm", "message": reason,
                })
                moved[0] = True
                return
        return False

    store.modify("kanban", _modify)
    return moved[0]


def get_waiting_context(task_id):
    """WAITING 카드의 전체 컨텍스트 반환 (activity_log, source_message_ids 등)."""
    data = store.load("kanban")
    for task in data.get("tasks", []):
        if task["id"] == task_id:
            return task
    return None


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
    kanban.json → kanban_archive.json.

    Returns list of archived task summaries for briefing report.
    """
    cutoff = datetime.now() - timedelta(hours=hours)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    to_archive = []

    # Phase 1: identify tasks to archive (read-only pass)
    def _identify(data):
        for task in data.get("tasks", []):
            if task["column"] == COL_DONE and task.get("updated_at", "") < cutoff_str:
                task["archived_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                to_archive.append(task)
        return False  # skip save

    store.modify("kanban", _identify)

    if not to_archive:
        return []

    # Phase 2: write archive file (separate file)
    archive = _load_archive()
    archive.extend(to_archive)
    if len(archive) > 200:
        archive = archive[-200:]
    _save_archive(archive)

    # Phase 3: remove archived tasks from kanban.json
    archive_ids = {t["id"] for t in to_archive}

    def _remove(data):
        data["tasks"] = [t for t in data.get("tasks", []) if t["id"] not in archive_ids]

    store.modify("kanban", _remove)

    return [
        {"id": t["id"], "title": t["title"], "done_at": t.get("updated_at", "")}
        for t in to_archive
    ]


def get_archive(limit=50):
    """Get archived tasks (newest first)."""
    archive = _load_archive()
    return list(reversed(archive))[:limit]
