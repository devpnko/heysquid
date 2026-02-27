"""Data polling -- loading messages.json, agent_status.json, stream.jsonl

Self-healing principle: return cache if any file is corrupted -> auto-refresh when file recovers.
"""

import json
import logging
import os
import subprocess
import time
from collections import deque
from datetime import datetime

from heysquid.core.agents import AGENTS, TOOL_EMOJI, SUBAGENT_MAP

from .utils import trunc

log = logging.getLogger("tui.poller")

# --- File paths ---
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(ROOT, "data")
STATUS_FILE = os.path.join(DATA_DIR, "agent_status.json")
KANBAN_FILE = os.path.join(DATA_DIR, "kanban.json")
AUTOMATIONS_FILE = os.path.join(DATA_DIR, "automations.json")
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")
STREAM_FILE = os.path.join(ROOT, "logs", "executor.stream.jsonl")
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
EXECUTOR_LOCK = os.path.join(DATA_DIR, "executor.lock")
EXECUTOR_PID_FILE = os.path.join(DATA_DIR, "executor.pid")
CLAUDE_PID_FILE = os.path.join(DATA_DIR, "claude.pid")

SQUAD_HISTORY_FILE = os.path.join(DATA_DIR, "squad_history.json")
CHAT_MAX_MESSAGES = 200
STREAM_BUFFER_SIZE = 200

# --- Stream agent tracking ---
_stream_active_agents: dict = {}


def _safe_load_json(path: str, cache: dict, key: str = "data"):
    """Safely load JSON file. Return cache on any exception. Reload only on mtime change."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return cache[key]

    if mtime <= cache["mtime"]:
        return cache[key]

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        cache["mtime"] = mtime
        cache[key] = data
        return data
    except Exception as e:
        # Any exception (UnicodeDecodeError, JSONDecodeError, OSError, ...)
        # Return cache. Don't update mtime -> auto-reload when file recovers.
        log.debug("Failed to load %s: %s", os.path.basename(path), e)
        return cache[key]


_status_cache: dict = {"mtime": 0.0, "data": {}}
_kanban_cache: dict = {"mtime": 0.0, "data": {}}
_automations_cache: dict = {"mtime": 0.0, "data": {}}
_workspaces_cache: dict = {"mtime": 0.0, "data": {}}


def load_agent_status() -> dict:
    """Load agent_status.json + merge separate files (kanban/automations/workspaces)."""
    base = _safe_load_json(STATUS_FILE, _status_cache)

    # Prefer separate files (latest data), fallback to base
    kanban = _safe_load_json(KANBAN_FILE, _kanban_cache)
    if kanban:
        base["kanban"] = kanban

    automations = _safe_load_json(AUTOMATIONS_FILE, _automations_cache)
    if automations:
        base["automations"] = automations

    workspaces = _safe_load_json(WORKSPACES_FILE, _workspaces_cache)
    if workspaces:
        base["workspaces"] = workspaces

    return base


def is_executor_live() -> bool:
    """Check if executor is running (based on claude PM process)."""
    procs = get_executor_processes()
    return procs["claude"]


# --- Executor process status ---
_proc_cache: dict = {"ts": 0.0, "data": {
    "executor": False, "claude": False, "caffeinate": False, "viewer": False,
}}


def _pid_alive(pid: int) -> bool:
    """Check if PID is alive (os.kill signal 0)."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _read_pids(path: str) -> list[int]:
    """Read PID list from PID file."""
    try:
        with open(path) as f:
            return [int(l.strip()) for l in f if l.strip().isdigit()]
    except (FileNotFoundError, ValueError):
        return []


def get_executor_processes() -> dict:
    """Status of 4 executor-related processes (5-second cache)."""
    now = time.time()
    if now - _proc_cache["ts"] < 5:
        return _proc_cache["data"]

    procs = {
        "executor": False,
        "claude": False,
        "caffeinate": False,
        "viewer": False,
    }

    # executor.pid
    for pid in _read_pids(EXECUTOR_PID_FILE):
        if _pid_alive(pid):
            procs["executor"] = True
            break

    # claude.pid (line 1: claude, line 2: caffeinate)
    pids = _read_pids(CLAUDE_PID_FILE)
    if len(pids) >= 1 and _pid_alive(pids[0]):
        procs["claude"] = True
    if len(pids) >= 2 and _pid_alive(pids[1]):
        procs["caffeinate"] = True

    # viewer: pgrep (tail -F executor.stream.jsonl)
    try:
        r = subprocess.run(
            ["pgrep", "-f", "tail.*executor.stream"],
            capture_output=True, timeout=2,
        )
        procs["viewer"] = r.returncode == 0
    except Exception:
        pass

    _proc_cache["ts"] = now
    _proc_cache["data"] = procs
    return procs


# --- Chat data polling ---
_chat_cache: dict = {"mtime": 0.0, "data": {"messages": []}, "messages": []}


def poll_chat_messages() -> list[dict]:
    """Poll chat messages from messages.json (mtime-based cache, self-healing)."""
    raw = _safe_load_json(MESSAGES_FILE, _chat_cache)
    if isinstance(raw, dict):
        msgs = raw.get("messages", [])
        chat_msgs = [m for m in msgs if m.get("type") in ("user", "bot")]
        _chat_cache["messages"] = chat_msgs[-CHAT_MAX_MESSAGES:]
    return _chat_cache["messages"]


_squad_history_cache: dict = {"mtime": 0.0, "data": []}


def load_squad_history() -> list[dict]:
    """Load squad_history.json (mtime cache, self-healing)."""
    return _safe_load_json(SQUAD_HISTORY_FILE, _squad_history_cache)


def invalidate_chat_cache():
    """Invalidate cache (for immediate refresh after message send)."""
    _chat_cache["mtime"] = 0.0


# --- Stream log polling ---

def load_stream_lines(last_pos: int, buffer: deque) -> int:
    """Read executor.stream.jsonl tail. Append new lines to buffer, return new position."""
    try:
        size = os.path.getsize(STREAM_FILE)
    except OSError:
        return last_pos

    if size < last_pos:
        last_pos = 0
        buffer.clear()

    if size == last_pos:
        return last_pos

    try:
        with open(STREAM_FILE, "r", encoding="utf-8", errors="replace") as f:
            f.seek(last_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = _parse_stream_event(json.loads(line))
                    if parsed:
                        if isinstance(parsed, list):
                            buffer.extend(parsed)
                        else:
                            buffer.append(parsed)
                except json.JSONDecodeError:
                    pass
            return f.tell()
    except OSError:
        return last_pos


def _parse_stream_event(d: dict):
    """JSONL event -> display [(time, emoji, agent, text), ...] list."""
    t = d.get("type", "")
    now = datetime.now().strftime("%H:%M")

    if t == "system":
        subtype = d.get("subtype", "")
        if subtype == "init":
            model = d.get("model", "?")
            return [(now, "🚀", "system", f"Session start ({model})")]

    elif t == "assistant":
        content = d.get("message", {}).get("content", [])
        results = []
        for c in content:
            if c.get("type") == "text":
                text = c["text"].strip()
                if text:
                    results.append((now, "🦑", "pm", trunc(text, 120)))
            elif c.get("type") == "tool_use":
                name = c.get("name", "?")
                inp = c.get("input", {})
                if name == "Task":
                    desc = inp.get("description", "")
                    agent_type = inp.get("subagent_type", "")
                    model = inp.get("model", "")
                    da = SUBAGENT_MAP.get(agent_type)
                    emoji = AGENTS[da]["emoji"] if da and da in AGENTS else "🎯"
                    label = agent_type or "agent"
                    model_str = f" ({model})" if model else ""
                    tool_id = c.get("id", "")
                    if tool_id:
                        _stream_active_agents[tool_id] = {
                            "type": label, "agent": da,
                            "model": model_str.strip(" ()"),
                            "start": datetime.now(),
                        }
                    lines = [
                        (now, "┌─", da or "pm", f"{emoji} [{label}]{model_str}"),
                        ("", "│", da or "pm", f"  Mission: {desc}"),
                    ]
                    prompt = inp.get("prompt", "")
                    if prompt:
                        for pl in prompt.strip().split("\n")[:3]:
                            pl = pl.strip()
                            if pl:
                                lines.append(("", "│", da or "pm", f"  > {trunc(pl, 70)}"))
                    lines.append(("", "│", da or "pm", ""))
                    results.extend(lines)
                else:
                    emoji = TOOL_EMOJI.get(name, "🔧")
                    detail = ""
                    if name == "Read":
                        detail = inp.get("file_path", "")
                    elif name == "Bash":
                        detail = inp.get("command", "")
                    elif name in ("Edit", "Write"):
                        detail = inp.get("file_path", "")
                    elif name == "Grep":
                        detail = f'"{inp.get("pattern", "")}"'
                    elif name == "Glob":
                        detail = inp.get("pattern", "")
                    elif name in ("WebSearch", "WebFetch"):
                        detail = inp.get("query", inp.get("url", ""))
                    else:
                        detail = str(inp)[:80]
                    results.append((now, emoji, "pm",
                                    f"{name} → {trunc(detail, 90)}"))
        return results if results else None

    elif t == "user":
        content = d.get("message", {}).get("content", [])
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                tool_id = c.get("tool_use_id", "")
                if tool_id in _stream_active_agents:
                    agent = _stream_active_agents.pop(tool_id)
                    elapsed = (datetime.now() - agent["start"]).total_seconds()
                    da = agent.get("agent") or "pm"
                    emoji = AGENTS[da]["emoji"] if da in AGENTS else "✅"
                    model_str = f" [{agent['model']}]" if agent.get("model") else ""
                    text = c.get("content", "")
                    lines = [
                        ("", "│", da, ""),
                        (now, "✅", da, f"└─ [{agent['type']}] Done ({elapsed:.1f}s){model_str}"),
                    ]
                    if isinstance(text, str) and text:
                        for rl in trunc(text, 150).split(". ")[:2]:
                            if rl.strip():
                                lines.append(("", " ", da, f"  → {rl.strip()}"))
                    return lines
        return None

    elif t == "result":
        cost = d.get("total_cost_usd", 0)
        dur = d.get("duration_ms", 0) / 1000
        turns = d.get("num_turns", 0)
        _stream_active_agents.clear()
        return [(now, "✨", "system",
                 f"Session end  ${cost:.4f} | {dur:.0f}s | {turns} turns")]

    return None
