"""데이터 폴링 — messages.json, agent_status.json, stream.jsonl 로딩"""

import json
import os
from collections import deque
from datetime import datetime

from heysquid.core.agents import AGENTS, TOOL_EMOJI, SUBAGENT_MAP

from .utils import trunc

# --- 파일 경로 ---
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATUS_FILE = os.path.join(ROOT, "data", "agent_status.json")
STREAM_FILE = os.path.join(ROOT, "logs", "executor.stream.jsonl")
MESSAGES_FILE = os.path.join(ROOT, "data", "messages.json")
EXECUTOR_LOCK = os.path.join(ROOT, "data", "executor.lock")

SQUAD_HISTORY_FILE = os.path.join(ROOT, "data", "squad_history.json")
CHAT_MAX_MESSAGES = 200
STREAM_BUFFER_SIZE = 200

# --- Stream 에이전트 추적 ---
_stream_active_agents: dict = {}


_status_cache = {"mtime": 0.0, "data": {}}


def load_agent_status() -> dict:
    """agent_status.json 로드 (mtime 기반 캐시)"""
    try:
        mtime = os.path.getmtime(STATUS_FILE)
    except OSError:
        return _status_cache["data"]

    if mtime <= _status_cache["mtime"]:
        return _status_cache["data"]

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _status_cache["mtime"] = mtime
        _status_cache["data"] = data
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return _status_cache["data"]


def is_executor_live() -> bool:
    """executor.lock 존재 여부"""
    return os.path.exists(EXECUTOR_LOCK)


# --- Chat 데이터 폴링 ---
_chat_cache = {"mtime": 0.0, "messages": []}


def poll_chat_messages() -> list[dict]:
    """messages.json에서 채팅 메시지 폴링 (mtime 기반 캐시)"""
    try:
        mtime = os.path.getmtime(MESSAGES_FILE)
    except OSError:
        return _chat_cache["messages"]

    if mtime <= _chat_cache["mtime"]:
        return _chat_cache["messages"]

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        msgs = data.get("messages", [])
        chat_msgs = [m for m in msgs if m.get("type") in ("user", "bot")]
        chat_msgs = chat_msgs[-CHAT_MAX_MESSAGES:]
        _chat_cache["mtime"] = mtime
        _chat_cache["messages"] = chat_msgs
    except (json.JSONDecodeError, OSError):
        pass

    return _chat_cache["messages"]


_squad_history_cache = {"mtime": 0.0, "data": []}


def load_squad_history() -> list[dict]:
    """squad_history.json 로드 (mtime 캐시)"""
    try:
        mtime = os.path.getmtime(SQUAD_HISTORY_FILE)
    except OSError:
        return _squad_history_cache["data"]

    if mtime <= _squad_history_cache["mtime"]:
        return _squad_history_cache["data"]

    try:
        with open(SQUAD_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        _squad_history_cache["mtime"] = mtime
        _squad_history_cache["data"] = data
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        return _squad_history_cache["data"]


def invalidate_chat_cache():
    """캐시 무효화 (메시지 전송 후 즉시 갱신 위해)"""
    _chat_cache["mtime"] = 0.0


# --- Stream 로그 폴링 ---

def load_stream_lines(last_pos: int, buffer: deque) -> int:
    """executor.stream.jsonl tail 읽기. 새 줄을 buffer에 추가, 새 position 반환."""
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
    """JSONL 이벤트 → 표시용 [(time, emoji, agent, text), ...] 리스트"""
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
                        ("", "│", da or "pm", f"  임무: {desc}"),
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
                        (now, "✅", da, f"└─ [{agent['type']}] 완료 ({elapsed:.1f}초){model_str}"),
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
                 f"Session end  ${cost:.4f} | {dur:.0f}s | {turns}턴")]

    return None
