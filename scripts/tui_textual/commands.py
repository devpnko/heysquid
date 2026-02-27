"""Command execution -- message sending, squad management, executor control"""

import json
import os
import shlex
import subprocess
import time
from collections import deque
from datetime import datetime

from heysquid.core.agents import AGENTS, KRAKEN_CREW_NAMES

from .utils import AGENT_ORDER, parse_mentions
from .data_poller import (
    ROOT, STATUS_FILE, MESSAGES_FILE, EXECUTOR_LOCK,
    invalidate_chat_cache,
)

# -- Command registry ---------------------------------------------------
COMMAND_REGISTRY = {
    "stop":     {"desc": "Stop current task"},
    "resume":   {"desc": "Restart executor"},
    "doctor":   {"desc": "System diagnostics"},
    "skill":    {"desc": "List/run skills"},
    "merge":    {"desc": "Merge kanban cards (/merge K1 K2)"},
    "done":     {"desc": "Mark card as Done (/done K1 or /done all)"},
    "clean":    {"desc": "Mark all active cards as Done"},
    "del":      {"desc": "Delete card (/del K1)"},
    "move":     {"desc": "Move card to column (/move K1 waiting)"},
    "info":     {"desc": "View card details (/info K1)"},
    "squid":    {"desc": "Start Squid discussion"},
    "kraken":   {"desc": "Start Kraken discussion"},
    "endsquad": {"desc": "End discussion"},
    "dashboard": {"desc": "Open dashboard"},
}

EXECUTOR_SCRIPT = os.path.join(ROOT, "scripts", "executor.sh")
DASHBOARD_HTML = os.path.join(ROOT, "data", "dashboard.html")
INTERRUPTED_FILE = os.path.join(ROOT, "data", "interrupted.json")
WORKING_LOCK_FILE = os.path.join(ROOT, "data", "working.json")
CLAUDE_PIDFILE = os.path.join(ROOT, "data", "claude.pid")


def _is_pm_alive() -> bool:
    """Check if PM (claude) process is alive -- same logic as executor.sh is_pm_alive."""
    # 1st: caffeinate pattern
    if subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True,
    ).returncode == 0:
        return True
    # 2nd: PID file
    if os.path.exists(CLAUDE_PIDFILE):
        try:
            with open(CLAUDE_PIDFILE, "r") as f:
                for line in f:
                    pid = line.strip()
                    if pid and subprocess.run(
                        ["kill", "-0", pid], capture_output=True
                    ).returncode == 0:
                        return True
        except Exception:
            pass
    return False

# Load BOT_TOKEN from .env
try:
    from dotenv import load_dotenv
    from heysquid.core.config import get_env_path
    load_dotenv(get_env_path())
except ImportError:
    pass
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.heic', '.tiff', '.svg'}


def _make_file_entry(path: str) -> dict:
    """Create image file metadata dict."""
    return {
        "type": "photo",
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "size": os.path.getsize(path),
    }


def _is_image_file(path: str) -> bool:
    """Check image extension + file existence."""
    _, ext = os.path.splitext(path)
    return ext.lower() in IMAGE_EXTENSIONS and os.path.isfile(path)


def extract_image_paths(text: str) -> tuple[str, list[dict]]:
    """Extract image file paths from text. Returns (cleaned text, files list).

    3-stage strategy:
    1) shlex -- backslash escapes, quoted paths (macOS drag-and-drop)
    2) Reassemble paths with spaces -- for Textual TextArea etc. without escaping
    3) Simple split fallback
    """
    # Stage 1: shlex (escape/quote handling)
    try:
        tokens = shlex.split(text)
    except ValueError:
        tokens = text.split()

    files = []
    clean_parts = []

    for token in tokens:
        expanded = os.path.expanduser(token)
        if _is_image_file(expanded):
            files.append(_make_file_entry(expanded))
        else:
            clean_parts.append(token)

    if files:
        return " ".join(clean_parts), files

    # Stage 2: Reassemble paths with spaces
    # e.g. "check this /path/to/screenshot 2026-02-23 12.04.09.png"
    # -> rejoin tokens split by shlex, from / start to .extension
    raw_tokens = text.split()
    used = set()

    for i, token in enumerate(raw_tokens):
        if i in used:
            continue
        expanded_start = os.path.expanduser(token)
        if not (expanded_start.startswith("/") or expanded_start.startswith("~")):
            continue
        # Try extending from this token forward to find an image file
        candidate = expanded_start
        for j in range(i + 1, len(raw_tokens) + 1):
            if _is_image_file(candidate):
                files.append(_make_file_entry(candidate))
                used.update(range(i, j))
                break
            if j < len(raw_tokens):
                candidate = candidate + " " + raw_tokens[j]

    if files:
        clean_parts = [t for idx, t in enumerate(raw_tokens) if idx not in used]
        return " ".join(clean_parts), files

    # No images found
    return text, []


def _get_real_user_info(messages: list[dict]) -> dict | None:
    """Look up real user info from existing Telegram messages."""
    for msg in reversed(messages):
        cid = msg.get("chat_id", 0)
        if isinstance(cid, int) and cid > 0 and msg.get("source") != "tui":
            return {
                "chat_id": cid,
                "user_id": msg.get("user_id", 0),
                "username": msg.get("username", "tui"),
                "first_name": msg.get("first_name", "TUI"),
            }
    return None


def inject_local_message(text: str, files: list[dict] | None = None) -> int:
    """Inject TUI message into messages.json (flock atomic)."""
    from heysquid.channels._msg_store import load_and_modify, load_telegram_messages

    # Look up user_info first (read-only)
    data = load_telegram_messages()
    user_info = _get_real_user_info(data.get("messages", []))
    if user_info is None:
        allowed = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        fallback_id = allowed.split(",")[0].strip() if allowed else ""
        if fallback_id.isdigit():
            user_info = {
                "chat_id": int(fallback_id),
                "user_id": int(fallback_id),
                "username": "tui",
                "first_name": "Commander",
            }

    new_id = None

    def _inject(data):
        nonlocal new_id
        tui_ids = [
            m["message_id"] for m in data.get("messages", [])
            if isinstance(m.get("message_id"), int) and m["message_id"] < 0
        ]
        new_id = min(tui_ids) - 1 if tui_ids else -1

        message = {
            "message_id": new_id,
            "type": "user",
            "channel": "tui",
            "user_id": user_info["user_id"] if user_info else 0,
            "username": user_info["username"] if user_info else "tui",
            "first_name": user_info["first_name"] if user_info else "TUI",
            "last_name": "",
            "chat_id": user_info["chat_id"] if user_info else 0,
            "text": text,
            "files": files or [],
            "location": None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "processed": False,
            "source": "tui",
            "mentions": parse_mentions(text),
        }
        data["messages"].append(message)
        return data

    load_and_modify(_inject)

    # Broadcast to all active channels (full sync)
    _broadcast_to_channels(text)

    invalidate_chat_cache()
    return new_id


def _broadcast_to_channels(text: str):
    """Broadcast TUI message to all active channels."""
    try:
        from heysquid.channels._router import broadcast_user_message
        broadcast_user_message(text, source_channel="tui", sender_name="COMMANDER")
    except Exception as e:
        # TUI message works even if broadcast fails
        print(f"[WARN] TUI broadcast failed: {e}")


def _kill_executor() -> bool:
    """Kill executor Claude process -- same logic as executor.sh kill_all_pm."""
    killed = False
    pidfile = os.path.join(ROOT, "data", "claude.pid")

    # 1st: PID file (most reliable -- catches orphan claude too)
    if os.path.exists(pidfile):
        try:
            with open(pidfile, "r") as f:
                for line in f:
                    pid = line.strip()
                    if pid:
                        subprocess.run(["kill", pid], capture_output=True)
                        killed = True
        except Exception:
            pass

    # 2nd: caffeinate pattern -> kill parent (claude)
    try:
        result = subprocess.run(
            ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            for cafe_pid in result.stdout.strip().split("\n"):
                cafe_pid = cafe_pid.strip()
                if cafe_pid:
                    # caffeinate's parent = claude
                    ppid_result = subprocess.run(
                        ["ps", "-p", cafe_pid, "-o", "ppid="],
                        capture_output=True, text=True,
                    )
                    parent = ppid_result.stdout.strip()
                    if parent:
                        subprocess.run(["kill", parent], capture_output=True)
                        killed = True
                    subprocess.run(["kill", cafe_pid], capture_output=True)
                    killed = True
    except Exception:
        pass

    # 3rd pass: pkill fallback
    subprocess.run(["pkill", "-f", "append-system-prompt-file"], capture_output=True)

    # force kill -- kill -9 survivors after 2 seconds
    if killed:
        import time
        time.sleep(2)
        if os.path.exists(pidfile):
            try:
                with open(pidfile, "r") as f:
                    for line in f:
                        pid = line.strip()
                        if pid:
                            subprocess.run(["kill", "-0", pid], capture_output=True)
                            subprocess.run(["kill", "-9", pid], capture_output=True)
            except Exception:
                pass
        subprocess.run(["pkill", "-9", "-f", "append-system-prompt-file"], capture_output=True)

    # Delete PID file
    try:
        if os.path.exists(pidfile):
            os.remove(pidfile)
    except OSError:
        pass

    try:
        if os.path.exists(EXECUTOR_LOCK):
            os.remove(EXECUTOR_LOCK)
    except OSError:
        pass

    working_info = None
    try:
        if os.path.exists(WORKING_LOCK_FILE):
            with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
                working_info = json.load(f)
            os.remove(WORKING_LOCK_FILE)
    except Exception:
        pass

    interrupted_data = {
        "interrupted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": "TUI /stop",
        "by_user": "TUI",
        "chat_id": 0,
        "previous_work": None,
    }
    if working_info:
        interrupted_data["previous_work"] = {
            "instruction": working_info.get("instruction_summary", ""),
            "started_at": working_info.get("started_at", ""),
            "message_id": working_info.get("message_id"),
        }

    os.makedirs(os.path.dirname(INTERRUPTED_FILE), exist_ok=True)
    with open(INTERRUPTED_FILE, "w", encoding="utf-8") as f:
        json.dump(interrupted_data, f, ensure_ascii=False, indent=2)

    # Mark unprocessed messages as processed (same as listener's _handle_stop_command)
    try:
        from heysquid.channels._msg_store import load_and_modify

        cleared = 0
        def _clear_unprocessed(data):
            nonlocal cleared
            for m in data.get("messages", []):
                if not m.get("processed", False):
                    m["processed"] = True
                    cleared += 1
            return data
        load_and_modify(_clear_unprocessed)
    except Exception:
        pass

    return killed


def _resume_executor() -> tuple[bool, str]:
    """Run executor.sh in background."""
    if os.path.exists(EXECUTOR_LOCK):
        return False, "executor already running"
    if not os.path.exists(EXECUTOR_SCRIPT):
        return False, "executor.sh not found"

    log_dir = os.path.join(ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "executor.log")

    with open(log_file, "a") as lf:
        subprocess.Popen(
            ["bash", EXECUTOR_SCRIPT],
            stdout=lf, stderr=lf,
            cwd=ROOT,
            start_new_session=True,
        )
    return True, "executor started"


def _clean_stale_lock_and_resume():
    """If executor.lock exists, check actual process; remove stale lock and restart."""
    if os.path.exists(EXECUTOR_LOCK):
        if not _is_pm_alive():
            try:
                os.remove(EXECUTOR_LOCK)
            except OSError:
                pass
            _resume_executor()
    else:
        _resume_executor()


def log_commander_message(text: str, stream_buffer: deque):
    """Log TUI commander message (Stream + Dashboard)."""
    now = datetime.now().strftime("%H:%M")
    stream_buffer.append((now, "🎖️", "commander", text))

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            status = json.load(f)
        if "mission_log" not in status:
            status["mission_log"] = []
        status["mission_log"].append({
            "time": now,
            "agent": "commander",
            "message": text,
        })
        status["mission_log"] = status["mission_log"][-50:]
        with open(STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _start_squid_squad(args_str: str, stream_buffer: deque) -> str:
    """Start Squid mode discussion."""
    from heysquid.dashboard import init_squad
    parts = args_str.strip().split()
    participants = []
    topic_parts = []
    for p in parts:
        if p.startswith("@") and p[1:] in [a for a in AGENT_ORDER if a != "pm"]:
            participants.append(p[1:])
        else:
            topic_parts.append(p)
    topic = " ".join(topic_parts) or "open discussion"
    if not participants:
        return "Specify participating agents: /squid @agent1 @agent2 topic"
    init_squad(topic, participants, mode="squid")
    names = " ".join(f"@{p}" for p in participants)
    log_commander_message(f"[Squad] Squid mode: {names} — {topic}", stream_buffer)
    return f"Squid Squad started: {names}"


def _start_kraken_squad(args_str: str, stream_buffer: deque) -> str:
    """Start Kraken mode."""
    from heysquid.dashboard import init_squad
    topic = args_str.strip() or "overall project evaluation"
    participants = [a for a in AGENT_ORDER if a != "pm"]
    init_squad(topic, participants, mode="kraken", virtual_experts=KRAKEN_CREW_NAMES)
    log_commander_message(f"[Squad] Kraken mode: all+Crew — {topic}", stream_buffer)
    return "Kraken Squad started: all+Kraken Crew"


def _run_doctor() -> str:
    """System diagnostics + auto repair."""
    lines = ["🩺 Doctor Report"]
    fixed = 0

    # 1. Check listeners (multi-channel)
    listener_configs = [
        ("TG", "telegram_listener", "com.heysquid.watcher.plist", None),
        ("SL", "slack_listener", "com.heysquid.slack.plist", "SLACK_BOT_TOKEN"),
        ("DC", "discord_listener", "com.heysquid.discord.plist", "DISCORD_BOT_TOKEN"),
    ]
    for tag, proc_name, plist_name, env_key in listener_configs:
        # Skip if token not configured
        if env_key and not os.getenv(env_key):
            continue

        has_proc = subprocess.run(
            ["pgrep", "-f", proc_name],
            capture_output=True,
        ).returncode == 0
        if has_proc:
            result = subprocess.run(
                ["pgrep", "-f", proc_name],
                capture_output=True, text=True,
            )
            pid = result.stdout.strip().split("\n")[0].strip()
            lines.append(f"✅ Listener [{tag}]: running (PID {pid})")
        else:
            plist = os.path.expanduser(f"~/Library/LaunchAgents/{plist_name}")
            if os.path.exists(plist):
                subprocess.run(["launchctl", "unload", plist], capture_output=True)
                time.sleep(1)
                subprocess.run(["launchctl", "load", plist], capture_output=True)
                time.sleep(2)
                alive = subprocess.run(
                    ["pgrep", "-f", proc_name],
                    capture_output=True,
                ).returncode == 0
                if alive:
                    lines.append(f"🔧 Listener [{tag}]: restarted")
                    fixed += 1
                else:
                    lines.append(f"❌ Listener [{tag}]: restart failed")
            else:
                lines.append(f"❌ Listener [{tag}]: not running (no plist)")

    # 2. Check executor lock
    if os.path.exists(EXECUTOR_LOCK):
        if _is_pm_alive():
            lines.append("✅ Lock: active (executor running)")
        else:
            try:
                os.remove(EXECUTOR_LOCK)
            except OSError:
                pass
            lines.append("🔧 Lock: stale lock removed")
            fixed += 1
    else:
        lines.append("✅ Lock: clean")

    # 3. Zombie processes (2+ executor.sh = abnormal)
    result = subprocess.run(
        ["pgrep", "-f", "bash.*executor.sh"],
        capture_output=True, text=True,
    )
    executor_pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    if len(executor_pids) > 1:
        for pid in executor_pids[:-1]:
            subprocess.run(["kill", pid], capture_output=True)
        lines.append(f"🔧 Zombies: killed {len(executor_pids) - 1} duplicate executor(s)")
        fixed += 1
    else:
        lines.append("✅ Zombies: clean")

    # 4. Orphan poll processes
    result = subprocess.run(
        ["pgrep", "-f", "poll_new_messages"],
        capture_output=True, text=True,
    )
    orphan_pids = [p.strip() for p in result.stdout.strip().split("\n") if p.strip()]
    if orphan_pids:
        for pid in orphan_pids:
            subprocess.run(["kill", pid], capture_output=True)
        lines.append(f"🔧 Orphans: killed {len(orphan_pids)} poll process(es)")
        fixed += 1
    else:
        lines.append("✅ Orphans: clean")

    # 5. Message queue
    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        unprocessed = [m for m in msgs if not m.get("processed")]
        stuck = [m for m in msgs if m.get("retry_count", 0) >= 3]
        if unprocessed or stuck:
            parts = []
            if unprocessed:
                parts.append(f"{len(unprocessed)} pending")
            if stuck:
                parts.append(f"{len(stuck)} stuck")
            lines.append(f"⚠️ Queue: {', '.join(parts)}")
        else:
            lines.append("✅ Queue: clean")
    except Exception:
        lines.append("✅ Queue: clean")

    # 6. Dashboard server
    dash_ok = subprocess.run(
        ["lsof", "-i", ":8420"],
        capture_output=True,
    ).returncode == 0
    lines.append(f"{'✅' if dash_ok else '⚠️'} Dashboard: {'running' if dash_ok else 'stopped'}")

    if fixed:
        lines.append(f"\nFixed {fixed} issue(s).")
    else:
        lines.append("\nAll systems healthy.")

    return "\n".join(lines)


def _run_skill_command(args_str: str) -> str:
    """List skills or run one manually."""
    from heysquid.skills import get_skill_registry, run_skill, SkillContext

    name = args_str.strip()
    registry = get_skill_registry()

    if not name:
        # Skill list
        if not registry:
            return "No registered skills"
        lines = ["Registered skills:"]
        for sname, meta in registry.items():
            enabled = meta.get("enabled", True)
            trigger = meta.get("trigger", "manual")
            schedule = meta.get("schedule", "")
            desc = meta.get("description", "")
            status = "off" if not enabled else "on"
            sched_info = f" ({schedule})" if schedule else ""
            lines.append(f"  {sname:<16} [{status}] {trigger}{sched_info}  {desc}")
        return "\n".join(lines)

    # Run skill
    if name not in registry:
        return f"Skill '{name}' not found. Use /skill to list"

    ctx = SkillContext(triggered_by="manual")
    result = run_skill(name, ctx)
    if result["ok"]:
        return f"Skill '{name}' completed"
    else:
        return f"Skill '{name}' failed: {result['error']}"


def _open_dashboard() -> str:
    """Open dashboard in default macOS browser (localhost server)."""
    subprocess.Popen(["open", "http://localhost:8420/dashboard.html"])
    return "Dashboard opened"


def _get_numbered_cards() -> list[dict]:
    """Return numbered kanban card list (non-done, non-automation, order preserved)."""
    from .data_poller import load_agent_status
    status = load_agent_status()
    tasks = status.get("kanban", {}).get("tasks", [])
    return [t for t in tasks if t.get("column") not in ("done", "automation")]


def _list_cards_display() -> str:
    """Active card K-ID list string."""
    cards = _get_numbered_cards()
    if not cards:
        return "No active cards"
    lines = ["Kanban card list:"]
    for c in cards:
        sid = c.get("short_id", "?")
        col = c.get("column", "?")[:4].upper()
        title = c.get("title", "")[:40]
        lines.append(f"  {sid} [{col}] {title}")
    return "\n".join(lines)


def _resolve_args(args_str: str) -> list[dict] | str:
    """Parse space-separated K-IDs into card list. Returns error string on failure."""
    from heysquid.dashboard.kanban import resolve_card
    parts = args_str.strip().split()
    cards = []
    for p in parts:
        card = resolve_card(p)
        if not card:
            return f"Card not found: {p}"
        cards.append(card)
    return cards


def _merge_kanban_cards(args_str: str) -> str:
    """Merge kanban cards. /merge K1 K2 -> merge K1 into K2."""
    from heysquid.dashboard.kanban import resolve_card
    parts = args_str.strip().split()
    if len(parts) != 2:
        return _list_cards_display() + "\n\nUsage: /merge <source> <target> (K-ID or number)"

    # Support K-ID or number
    def _find_card(token):
        card = resolve_card(token)
        if card:
            return card
        try:
            num = int(token)
            cards = _get_numbered_cards()
            if 1 <= num <= len(cards):
                return cards[num - 1]
        except ValueError:
            pass
        return None

    src = _find_card(parts[0])
    tgt = _find_card(parts[1])
    if not src:
        return f"Card not found: {parts[0]}"
    if not tgt:
        return f"Card not found: {parts[1]}"
    if src["id"] == tgt["id"]:
        return "Cannot merge a card with itself"

    from heysquid.dashboard.kanban import merge_kanban_tasks
    ok = merge_kanban_tasks(src["id"], tgt["id"])
    if ok:
        src_sid = src.get("short_id", "?")
        tgt_sid = tgt.get("short_id", "?")
        return f"✓ {src_sid} → {tgt_sid} merged"
    return "Merge failed (card not found)"


def _done_kanban_card(args_str: str) -> str:
    """Mark card as Done. /done K1 or /done all"""
    arg = args_str.strip().lower()
    if not arg:
        return _list_cards_display() + "\n\nUsage: /done <K-ID> or /done all"
    if arg == "all":
        return _clean_kanban_cards()
    resolved = _resolve_args(args_str)
    if isinstance(resolved, str):
        return resolved
    from heysquid.dashboard.kanban import move_kanban_task
    done_ids = []
    for card in resolved:
        if move_kanban_task(card["id"], "done"):
            done_ids.append(card.get("short_id", card["id"]))
    if done_ids:
        return f"✓ {', '.join(done_ids)} marked as Done"
    return "Operation failed"


def _clean_kanban_cards() -> str:
    """Mark all active cards as Done."""
    from heysquid.dashboard.kanban import move_kanban_task
    cards = _get_numbered_cards()
    if not cards:
        return "No active cards -- already clean!"
    count = 0
    for c in cards:
        if move_kanban_task(c["id"], "done"):
            count += 1
    return f"✓ {count} card(s) all marked as Done"


def _del_kanban_card(args_str: str) -> str:
    """Delete card. /del K1"""
    if not args_str.strip():
        return _list_cards_display() + "\n\nUsage: /del <K-ID>"
    resolved = _resolve_args(args_str)
    if isinstance(resolved, str):
        return resolved
    from heysquid.dashboard.kanban import delete_kanban_task
    deleted = []
    for card in resolved:
        if delete_kanban_task(card["id"]):
            deleted.append(card.get("short_id", card["id"]))
    if deleted:
        return f"✓ {', '.join(deleted)} deleted"
    return "Delete failed"


def _move_kanban_card(args_str: str) -> str:
    """Move card to column. /move K1 waiting"""
    parts = args_str.strip().split()
    if len(parts) != 2:
        return "Usage: /move <K-ID> <column>\nColumns: todo, in_progress(ip), waiting(wait), done"
    from heysquid.dashboard.kanban import resolve_card, move_kanban_task
    card = resolve_card(parts[0])
    if not card:
        return f"Card not found: {parts[0]}"
    col = parts[1].lower()
    col_aliases = {"prog": "in_progress", "ip": "in_progress", "wait": "waiting", "tw": "todo"}
    col = col_aliases.get(col, col)
    if col not in ("todo", "in_progress", "waiting", "done"):
        return f"Invalid column: {parts[1]}\nAvailable: todo, in_progress(ip), waiting(wait), done"
    sid = card.get("short_id", card["id"])
    ok = move_kanban_task(card["id"], col)
    if ok:
        return f"✓ {sid} → {col}"
    return "Move failed"


def _info_kanban_card(args_str: str) -> str:
    """View card details. /info K1"""
    if not args_str.strip():
        return _list_cards_display() + "\n\nUsage: /info <K-ID>"
    from heysquid.dashboard.kanban import resolve_card
    card = resolve_card(args_str.strip())
    if not card:
        return f"Card not found: {args_str.strip()}"
    sid = card.get("short_id", "?")
    lines = [
        f"── {sid} ──",
        f"Title: {card.get('title', '')}",
        f"Column: {card.get('column', '?')}",
        f"Created: {card.get('created_at', '?')}",
        f"Updated: {card.get('updated_at', '?')}",
    ]
    tags = card.get("tags", [])
    if tags:
        lines.append(f"Tags: {', '.join(tags)}")
    logs = card.get("activity_log", [])
    if logs:
        lines.append(f"Logs: {len(logs)} entries")
        for entry in logs[-5:]:
            lines.append(f"  [{entry.get('time','')}] {entry.get('agent','')}: {entry.get('message','')}")
    result = card.get("result")
    if result:
        lines.append(f"Result: {str(result)[:100]}")
    return "\n".join(lines)


def dispatch_command(raw: str, stream_buffer: deque) -> str | None:
    """Unified command dispatch. '/cmd args' -> call handler. Returns None if not a command."""
    cmd = raw.strip()
    if not cmd.startswith("/"):
        return None
    cmd = cmd[1:]
    parts = cmd.split(None, 1)
    name = parts[0].lower() if parts else ""
    args = parts[1] if len(parts) > 1 else ""

    if name == "stop":
        # Force session memory update before kill (preserve context)
        try:
            from heysquid.memory.session import compact_session_memory, save_session_summary
            compact_session_memory()
            save_session_summary()
        except Exception:
            pass
        killed = _kill_executor()
        return "Task stopped (session memory saved)" if killed else "No running tasks"

    if name == "resume":
        ok, msg = _resume_executor()
        return msg

    if name == "doctor":
        return _run_doctor()

    if name == "skill":
        return _run_skill_command(args)

    if name == "merge":
        return _merge_kanban_cards(args)

    if name == "done":
        return _done_kanban_card(args)

    if name == "clean":
        return _clean_kanban_cards()

    if name == "del":
        return _del_kanban_card(args)

    if name == "move":
        return _move_kanban_card(args)

    if name == "info":
        return _info_kanban_card(args)

    if name == "squid":
        return _start_squid_squad(args, stream_buffer)

    if name == "kraken":
        return _start_kraken_squad(args, stream_buffer)

    if name == "dashboard":
        return _open_dashboard()

    if name == "endsquad":
        from heysquid.dashboard import clear_squad
        clear_squad()
        return "Squad ended"

    return None  # Unknown command


def send_chat_message(text: str, stream_buffer: deque) -> str:
    """Handle message sending in Chat mode. Returns flash message."""
    text = text.strip()
    if not text:
        return ""

    result = dispatch_command(text, stream_buffer)
    if result is not None:
        return result

    # Detect image paths
    clean_text, files = extract_image_paths(text)
    display_text = clean_text or "(image)"

    mid = inject_local_message(display_text, files=files)
    mentions = parse_mentions(display_text)
    log_commander_message(display_text, stream_buffer)

    _clean_stale_lock_and_resume()

    if files:
        names = ", ".join(f["name"] for f in files)
        suffix = f" (🖼️ {names})"
        if mentions:
            return f"✓ Sent → {' '.join('@' + m for m in mentions)}{suffix}"
        return f"✓ Sent{suffix}"

    if mentions:
        return f"✓ Sent → {' '.join('@' + m for m in mentions)}"
    return "✓ Sent"


def execute_command(cmd: str, stream_buffer: deque) -> str:
    """Parse and execute command (/ prefix mode)."""
    cmd = cmd.strip()
    if not cmd:
        return ""

    # dispatch_command expects /prefix
    result = dispatch_command("/" + cmd, stream_buffer)
    if result is not None:
        return result

    # Default: send message
    mid = inject_local_message(cmd)
    mentions = parse_mentions(cmd)
    log_commander_message(cmd, stream_buffer)
    _clean_stale_lock_and_resume()
    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)} (id={mid})"
    return f"Message sent (id={mid})"
