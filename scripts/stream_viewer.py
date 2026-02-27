#!/usr/bin/env python3
"""
squid agent box -- Real-time stream viewer + Telegram broadcast + Dashboard sync.

Usage:
    tail -f logs/executor.stream.jsonl | python3 scripts/stream_viewer.py

    or:
    bash scripts/monitor.sh

Outputs to TUI as before while simultaneously sending key events to Telegram channel.
Auto-disabled if TELEGRAM_BOT_TOKEN + TELEGRAM_AGENTBOX_CHANNEL_ID are not set in .env.
"""

import sys
import os
import json
import asyncio
import threading
import queue
from datetime import datetime

# heysquid package import (run with pip install -e or venv)
# sys.path.insert not needed -- package is installed

# Load .env (config-based)
from heysquid.core.config import get_env_path as _get_env_path
_env_path = _get_env_path()
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

# agents.py — Single Source of Truth
from heysquid.agents import AGENTS, SUBAGENT_MAP, TOOL_EMOJI, get_emoji, get_role_emoji

# Dashboard integration (graceful fallback)
try:
    from heysquid.agent_dashboard import (
        add_mission_log, dispatch_agent, recall_agent,
        update_agent_status, set_pm_speech, set_current_task
    )
    DASHBOARD_ENABLED = True
except ImportError:
    DASHBOARD_ENABLED = False

# Model aliases
MODEL_NAMES = {
    "haiku": "Haiku",
    "sonnet": "Sonnet",
    "opus": "Opus",
}

# Active agent tracking (tool_use id -> info)
active_agents = {}

# Desk inference keywords
DESK_KEYWORDS = {
    "thread": ["thread", "threads"],
    "news": ["news", "briefing"],
    "trading": ["trading", "trade"],
    "marketing": ["marketing"],
    "shorts": ["shorts", "short"],
}


def infer_desk(prompt):
    """Auto-map prompt keywords to desk."""
    prompt_lower = prompt.lower()
    for desk, keywords in DESK_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return desk
    return "thread"  # default


def dashboard_log(agent, message):
    """Log to dashboard mission_log (ignored if disabled)."""
    if DASHBOARD_ENABLED:
        try:
            add_mission_log(agent, message)
        except Exception:
            pass


def dashboard_dispatch(agent_name, desk, task):
    """Reflect agent dispatch to dashboard."""
    if DASHBOARD_ENABLED:
        try:
            dispatch_agent(agent_name, desk, task)
        except Exception:
            pass


def dashboard_recall(agent_name, message='Task complete'):
    """Reflect agent recall to dashboard."""
    if DASHBOARD_ENABLED:
        try:
            recall_agent(agent_name, message)
        except Exception:
            pass


# ─── PM State Tracking ───────────────────────────────────

pm_state = "idle"  # idle | thinking | chatting | working
_thinking_timer = None
_thinking_shown = False


def _set_pm_state(new_state):
    """PM state transition + dashboard update."""
    global pm_state, _thinking_timer, _thinking_shown
    if _thinking_timer:
        _thinking_timer.cancel()
        _thinking_timer = None
    _thinking_shown = False
    pm_state = new_state
    dashboard_update_pm(new_state)


def _schedule_thinking():
    """Schedule thinking display after 2s (generating next response after tool result)."""
    global _thinking_timer
    if _thinking_timer:
        _thinking_timer.cancel()
    _thinking_timer = threading.Timer(2.0, _show_thinking)
    _thinking_timer.daemon = True
    _thinking_timer.start()


def _show_thinking():
    """Display thinking in TUI if no events for 2+ seconds."""
    global _thinking_shown
    if pm_state == "thinking":
        _thinking_shown = True
        print(f"\033[90m[{fmt_time()}] 🦑 💭 thinking...\033[0m")
        dashboard_update_pm("thinking", "💭 Thinking...")


def dashboard_update_pm(status, speech=""):
    """Reflect PM state to agent_status.json."""
    if DASHBOARD_ENABLED:
        try:
            update_agent_status("pm", status, speech)
            if speech:
                set_pm_speech(speech)
        except Exception:
            pass


# ─── Telegram Broadcaster ────────────────────────────────

class TelegramBroadcaster:
    """Async broadcast key events to Telegram channel. Non-blocking for terminal output."""

    def __init__(self, bot_token, channel_id):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self._bot = None
        self._queue = queue.Queue(maxsize=100)
        self.enabled = bool(bot_token and channel_id)
        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()

    def _get_bot(self):
        if self._bot is None:
            from telegram import Bot
            self._bot = Bot(token=self.bot_token)
        return self._bot

    def send(self, text):
        """Non-blocking. Enqueue and return immediately."""
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def _worker(self):
        """Consume queue in background thread -> Telegram API calls."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            msg = self._queue.get()
            if msg is None:
                break
            try:
                bot = self._get_bot()
                loop.run_until_complete(bot.send_message(
                    chat_id=self.channel_id, text=msg,
                    parse_mode="Markdown"
                ))
            except Exception as e:
                # Markdown parse failure -> retry as plain text
                if "parse" in str(e).lower():
                    try:
                        bot = self._get_bot()
                        loop.run_until_complete(bot.send_message(
                            chat_id=self.channel_id, text=msg,
                            parse_mode=None
                        ))
                    except Exception as e2:
                        print(f"[Telegram Error] {e2}", file=sys.stderr)
                else:
                    print(f"[Telegram Error] {e}", file=sys.stderr)
        loop.close()


# Broadcaster instance (auto-disabled if no token/channel ID)
broadcaster = TelegramBroadcaster(
    bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
    channel_id=os.environ.get("TELEGRAM_AGENTBOX_CHANNEL_ID", ""),
)


# ─── Helpers ──────────────────────────────────────────────

def fmt_time():
    return datetime.now().strftime("%H:%M:%S")


def truncate(text, maxlen=120):
    text = text.replace("\n", " ").strip()
    if len(text) > maxlen:
        return text[:maxlen] + "..."
    return text


def is_standby(text):
    """Detect standby loop messages."""
    return "[STANDBY]" in text


# ─── Main ─────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  🦑 squid agent box")
    if broadcaster.enabled:
        print("  📡 Telegram broadcast: ON")
    else:
        print("  📡 Telegram broadcast: OFF")
    print(f"  🖥️  Dashboard sync: {'ON' if DASHBOARD_ENABLED else 'OFF'}")
    print("  Ctrl+C to exit")
    print("=" * 55)
    print()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            try:
                _process_event(d)
            except Exception as e:
                print(f"\033[31m[{fmt_time()}] [ERROR] {e}\033[0m", file=sys.stderr)
                continue

    except KeyboardInterrupt:
        print("\n\nExiting.")
    except BrokenPipeError:
        pass
    except Exception as e:
        print(f"\033[31m[FATAL] stream_viewer: {e}\033[0m", file=sys.stderr)


def _process_event(d):
    """Process a single stream-json event (exceptions caught by caller)."""
    t = d.get("type", "")

    if t == "system":
        subtype = d.get("subtype", "")
        if subtype == "init":
            sid = d.get("session_id", "?")[:12]
            model = d.get("model", "?")
            _set_pm_state("idle")
            print(f"\033[36m[{fmt_time()}] [SESSION]\033[0m {sid}... ({model})")
            broadcaster.send(f"🚀 *Session Start* {model}")
            dashboard_log('system', f'🚀 Session start ({model})')

    elif t == "assistant":
        content = d.get("message", {}).get("content", [])
        for c in content:
            if c["type"] == "text":
                text = c["text"].strip()
                if text:
                    if is_standby(text):
                        _set_pm_state("idle")
                        print(f"\033[90m[{fmt_time()}] 🦑 ⏳ {truncate(text, 60)}\033[0m")
                        broadcaster.send(f"⏳ {truncate(text, 100)}")
                        dashboard_log('pm', f'💤 {truncate(text, 40)}')
                    else:
                        _set_pm_state("chatting")
                        dashboard_update_pm("chatting", f"💬 {truncate(text, 30)}")
                        print(f"\033[33m[{fmt_time()}] 🦑 💬\033[0m {text}")
                        broadcaster.send(f"🦑 {truncate(text, 200)}")
                        dashboard_log('pm', f'💬 {truncate(text, 40)}')

            elif c["type"] == "tool_use":
                _set_pm_state("working")
                name = c.get("name", "?")
                inp = c.get("input", {})
                tool_id = c.get("id", "")

                if name == "Task":
                    desc = inp.get("description", "")
                    agent_type = inp.get("subagent_type", "")
                    model = inp.get("model", "")
                    prompt = inp.get("prompt", "")

                    model_label = MODEL_NAMES.get(model, model) if model else ""

                    # Emoji mapping based on agents.py
                    dashboard_agent = SUBAGENT_MAP.get(agent_type)
                    if dashboard_agent:
                        emoji = get_emoji(dashboard_agent)
                        role_emoji = get_role_emoji(dashboard_agent)
                    else:
                        emoji = TOOL_EMOJI.get(agent_type, "🤖")
                        role_emoji = ""
                    role_label = agent_type if agent_type else "agent"

                    # Agent tracking
                    active_agents[tool_id] = {
                        "type": role_label,
                        "dashboard_agent": dashboard_agent,
                        "model": model_label,
                        "desc": desc,
                        "start": datetime.now(),
                        "prompt": prompt,
                    }

                    print()
                    print(f"\033[34m[{fmt_time()}] ┌─ {emoji} [{role_label}]", end="")
                    if model_label:
                        print(f" ({model_label})", end="")
                    print(f"\033[0m")
                    print(f"\033[34m│\033[0m  Mission: {desc}")
                    if prompt:
                        lines = prompt.strip().split("\n")
                        preview = lines[:3]
                        for pl in preview:
                            print(f"\033[34m│\033[0m  \033[90m> {truncate(pl, 80)}\033[0m")
                        if len(lines) > 3:
                            print(f"\033[34m│\033[0m  \033[90m  ... (+{len(lines)-3} lines)\033[0m")
                    print(f"\033[34m│\033[0m")

                    # Broadcast: agent delegation
                    model_str = f" ({model_label})" if model_label else ""
                    broadcaster.send(f"{emoji} *{role_label}*{model_str} {desc}")

                    # Dashboard: agent dispatch
                    if dashboard_agent:
                        desk = infer_desk(prompt or desc)
                        log_msg = f"{emoji}{role_emoji} {truncate(desc, 35)}"
                        dashboard_dispatch(dashboard_agent, desk, desc)
                        dashboard_log(dashboard_agent, log_msg)

                elif name == "Read":
                    detail = inp.get("file_path", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 📖 Read → {detail}")
                    broadcaster.send(f"📖 Read → {truncate(detail, 80)}")
                    dashboard_log('pm', f'📖 Reading {os.path.basename(detail)}')
                elif name == "Bash":
                    cmd = inp.get("command", "")
                    if cmd.strip().startswith("sleep"):
                        print(f"\033[90m[{fmt_time()}] [TOOL] 💤 {cmd.strip()}\033[0m")
                        broadcaster.send(f"💤 {cmd.strip()}")
                    else:
                        print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 💻 Bash → {truncate(cmd, 80)}")
                        broadcaster.send(f"💻 Bash → {truncate(cmd, 80)}")
                        dashboard_log('pm', f'💻 {truncate(cmd, 35)}')
                elif name == "Edit":
                    fp = inp.get("file_path", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m ✏️  Edit → {fp}")
                    broadcaster.send(f"✏️ Edit → {truncate(fp, 80)}")
                    dashboard_log('pm', f'✏️ Editing {os.path.basename(fp)}')
                elif name == "Write":
                    fp = inp.get("file_path", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 📝 Write → {fp}")
                    broadcaster.send(f"📝 Write → {truncate(fp, 80)}")
                    dashboard_log('pm', f'📝 Writing {os.path.basename(fp)}')
                elif name == "Grep":
                    pat = inp.get("pattern", "")
                    path = inp.get("path", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 🔍 Grep → \"{pat}\" in {path}")
                    broadcaster.send(f"🔍 Grep → \"{pat}\" in {path}")
                    dashboard_log('pm', f'🔍 Searching "{truncate(pat, 20)}"')
                elif name == "Glob":
                    pat = inp.get("pattern", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 📂 Glob → {pat}")
                    broadcaster.send(f"📂 Glob → {pat}")
                    dashboard_log('pm', f'📂 Scanning {truncate(pat, 25)}')
                elif name == "WebSearch":
                    q = inp.get("query", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 🌐 WebSearch → \"{q}\"")
                    broadcaster.send(f"🌐 WebSearch → \"{q}\"")
                    dashboard_log('pm', f'🌐 Searching "{truncate(q, 25)}"')
                elif name == "WebFetch":
                    url = inp.get("url", "")
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m 🌐 WebFetch → {url}")
                    broadcaster.send(f"🌐 WebFetch → {url}")
                    dashboard_log('pm', f'🌐 Fetching web content')
                else:
                    detail = str(inp)
                    print(f"\033[35m[{fmt_time()}] [TOOL]\033[0m {name} → {truncate(detail, 80)}")
                    broadcaster.send(f"🔧 {name} → {truncate(detail, 80)}")

    elif t == "user":
        # tool result → PM is now thinking about next action
        _set_pm_state("thinking")
        _schedule_thinking()
        content = d.get("message", {}).get("content", [])
        for c in content:
            if isinstance(c, dict) and c.get("type") == "tool_result":
                tool_id = c.get("tool_use_id", "")
                text = c.get("content", "")

                # Agent completion matching
                if tool_id in active_agents:
                    agent = active_agents.pop(tool_id)
                    elapsed = (datetime.now() - agent["start"]).total_seconds()
                    da = agent.get("dashboard_agent")
                    emoji = get_emoji(da) if da else "🤖"

                    result_preview = ""
                    if isinstance(text, str) and text:
                        result_preview = truncate(text, 150)

                    print(f"\033[34m│\033[0m")
                    print(f"\033[34m└─ {emoji} [{agent['type']}] ✅ Done\033[0m ({elapsed:.1f}s)", end="")
                    if agent.get("model"):
                        print(f" [{agent['model']}]", end="")
                    print()
                    if result_preview:
                        lines = result_preview.split(". ")
                        for rl in lines[:2]:
                            if rl.strip():
                                print(f"   \033[90m→ {rl.strip()}\033[0m")
                    print()

                    # Broadcast: agent completion
                    model_str = f" [{agent['model']}]" if agent.get("model") else ""
                    broadcaster.send(f"✅ *{agent['type']}* Done {elapsed:.1f}s{model_str}")

                    # Dashboard: agent recall
                    if da:
                        dashboard_recall(da, f'✅ Complete ({elapsed:.1f}s)')

                elif isinstance(text, str) and len(text) > 0:
                    summary = truncate(text, 100)
                    if len(text) > 200:
                        print(f"\033[90m[{fmt_time()}] [Result] {summary}\033[0m")
                    broadcaster.send(f"→ {truncate(text, 150)}")

    elif t == "result":
        _set_pm_state("idle")
        cost = d.get("total_cost_usd", 0)
        dur = d.get("duration_ms", 0) / 1000
        turns = d.get("num_turns", 0)
        result_text = d.get("result", "")
        if len(result_text) > 100:
            result_text = result_text[:100] + "..."

        print()
        print("\033[32m" + "━" * 55 + "\033[0m")
        print(f"\033[32m[{fmt_time()}] [SESSION END]\033[0m 💰 ${cost:.4f} | ⏱ {dur:.1f}s | 🔄 {turns} turns")
        if result_text:
            print(f"\033[32m[Result]\033[0m {result_text}")
        print("\033[32m" + "━" * 55 + "\033[0m")
        print()

        broadcaster.send(f"✨ *Session Complete* ${cost:.4f} {dur:.0f}s {turns} turns")
        dashboard_log('system', f'✨ Session complete (${cost:.4f})')

        # Recall all agents
        for agent_name in active_agents.values():
            da = agent_name.get("dashboard_agent")
            if da:
                dashboard_recall(da, '✨ Session ended')
        active_agents.clear()


if __name__ == "__main__":
    main()
