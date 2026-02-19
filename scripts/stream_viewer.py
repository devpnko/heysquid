#!/usr/bin/env python3
"""
🦑 squid agent box — 실시간 스트림 뷰어 + Telegram 브로드캐스트 + Dashboard 동기화

사용법:
    tail -f logs/executor.stream.jsonl | python3 scripts/stream_viewer.py

    또는:
    bash scripts/monitor.sh

TUI에 기존처럼 출력하면서 핵심 이벤트만 Telegram 채널로 동시 전송.
TELEGRAM_BOT_TOKEN + TELEGRAM_AGENTBOX_CHANNEL_ID가 .env에 없으면 자동 비활성화.
"""

import sys
import os
import json
import asyncio
import threading
import queue
from datetime import datetime

# heysquid 패키지 import를 위한 경로 설정
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# .env 로드 (heysquid/.env)
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", "heysquid", ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

# agents.py — Single Source of Truth
from heysquid.agents import AGENTS, SUBAGENT_MAP, TOOL_EMOJI, get_emoji, get_role_emoji

# Dashboard 연동 (graceful fallback)
try:
    from heysquid.agent_dashboard import (
        add_mission_log, dispatch_agent, recall_agent,
        update_agent_status, set_pm_speech, set_current_task
    )
    DASHBOARD_ENABLED = True
except ImportError:
    DASHBOARD_ENABLED = False

# 모델 별명
MODEL_NAMES = {
    "haiku": "Haiku",
    "sonnet": "Sonnet",
    "opus": "Opus",
}

# 활성 에이전트 추적 (tool_use id → info)
active_agents = {}

# desk 추론 키워드
DESK_KEYWORDS = {
    "thread": ["thread", "스레드", "threads"],
    "news": ["news", "뉴스", "briefing", "브리핑"],
    "trading": ["trading", "트레이딩", "trade"],
    "marketing": ["marketing", "마케팅"],
    "shorts": ["shorts", "숏츠", "short"],
}


def infer_desk(prompt):
    """prompt 키워드 → desk 자동 매핑"""
    prompt_lower = prompt.lower()
    for desk, keywords in DESK_KEYWORDS.items():
        for kw in keywords:
            if kw in prompt_lower:
                return desk
    return "thread"  # 기본값


def dashboard_log(agent, message):
    """대시보드 mission_log에 기록 (비활성이면 무시)"""
    if DASHBOARD_ENABLED:
        try:
            add_mission_log(agent, message)
        except Exception:
            pass


def dashboard_dispatch(agent_name, desk, task):
    """대시보드에 에이전트 배치 반영"""
    if DASHBOARD_ENABLED:
        try:
            dispatch_agent(agent_name, desk, task)
        except Exception:
            pass


def dashboard_recall(agent_name, message='Task complete'):
    """대시보드에 에이전트 복귀 반영"""
    if DASHBOARD_ENABLED:
        try:
            recall_agent(agent_name, message)
        except Exception:
            pass


# ─── Telegram Broadcaster ────────────────────────────────

class TelegramBroadcaster:
    """핵심 이벤트를 Telegram 채널로 비동기 전송. 터미널 출력 블로킹 없음."""

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
        """Non-blocking. 큐에 넣고 즉시 리턴."""
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(text)
        except queue.Full:
            pass

    def _worker(self):
        """백그라운드 스레드에서 큐 소비 → Telegram API 호출"""
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
                # Markdown 파싱 실패 → plain text 재시도
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


# broadcaster 인스턴스 (토큰/채널ID 없으면 자동 비활성화)
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
    """대기 루프 메시지 판별"""
    return "[STANDBY]" in text or ("대기" in text and "루프" in text)


# ─── Main ─────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  🦑 squid agent box")
    if broadcaster.enabled:
        print("  📡 Telegram broadcast: ON")
    else:
        print("  📡 Telegram broadcast: OFF")
    print(f"  🖥️  Dashboard sync: {'ON' if DASHBOARD_ENABLED else 'OFF'}")
    print("  Ctrl+C로 종료")
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

            t = d.get("type", "")

            if t == "system":
                subtype = d.get("subtype", "")
                if subtype == "init":
                    sid = d.get("session_id", "?")[:12]
                    model = d.get("model", "?")
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
                                print(f"\033[90m[{fmt_time()}] 🦑 ⏳ {truncate(text, 60)}\033[0m")
                                broadcaster.send(f"⏳ {truncate(text, 100)}")
                                dashboard_log('pm', f'💤 {truncate(text, 40)}')
                            else:
                                print(f"\033[33m[{fmt_time()}] 🦑\033[0m {text}")
                                broadcaster.send(f"🦑 {truncate(text, 200)}")
                                dashboard_log('pm', f'🦑 {truncate(text, 40)}')

                    elif c["type"] == "tool_use":
                        name = c.get("name", "?")
                        inp = c.get("input", {})
                        tool_id = c.get("id", "")

                        if name == "Task":
                            desc = inp.get("description", "")
                            agent_type = inp.get("subagent_type", "")
                            model = inp.get("model", "")
                            prompt = inp.get("prompt", "")

                            model_label = MODEL_NAMES.get(model, model) if model else ""

                            # agents.py 기반 이모지 매핑
                            dashboard_agent = SUBAGENT_MAP.get(agent_type)
                            if dashboard_agent:
                                emoji = get_emoji(dashboard_agent)
                                role_emoji = get_role_emoji(dashboard_agent)
                            else:
                                emoji = TOOL_EMOJI.get(agent_type, "🤖")
                                role_emoji = ""
                            role_label = agent_type if agent_type else "agent"

                            # 에이전트 추적
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
                            print(f"\033[34m│\033[0m  임무: {desc}")
                            if prompt:
                                lines = prompt.strip().split("\n")
                                preview = lines[:3]
                                for pl in preview:
                                    print(f"\033[34m│\033[0m  \033[90m> {truncate(pl, 80)}\033[0m")
                                if len(lines) > 3:
                                    print(f"\033[34m│\033[0m  \033[90m  ... (+{len(lines)-3}줄)\033[0m")
                            print(f"\033[34m│\033[0m")

                            # broadcast: 에이전트 위임
                            model_str = f" ({model_label})" if model_label else ""
                            broadcaster.send(f"{emoji} *{role_label}*{model_str} {desc}")

                            # dashboard: 에이전트 배치
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
                content = d.get("message", {}).get("content", [])
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result":
                        tool_id = c.get("tool_use_id", "")
                        text = c.get("content", "")

                        # 에이전트 완료 매칭
                        if tool_id in active_agents:
                            agent = active_agents.pop(tool_id)
                            elapsed = (datetime.now() - agent["start"]).total_seconds()
                            da = agent.get("dashboard_agent")
                            emoji = get_emoji(da) if da else "🤖"

                            result_preview = ""
                            if isinstance(text, str) and text:
                                result_preview = truncate(text, 150)

                            print(f"\033[34m│\033[0m")
                            print(f"\033[34m└─ {emoji} [{agent['type']}] ✅ 완료\033[0m ({elapsed:.1f}초)", end="")
                            if agent.get("model"):
                                print(f" [{agent['model']}]", end="")
                            print()
                            if result_preview:
                                lines = result_preview.split(". ")
                                for rl in lines[:2]:
                                    if rl.strip():
                                        print(f"   \033[90m→ {rl.strip()}\033[0m")
                            print()

                            # broadcast: 에이전트 완료
                            model_str = f" [{agent['model']}]" if agent.get("model") else ""
                            broadcaster.send(f"✅ *{agent['type']}* 완료 {elapsed:.1f}s{model_str}")

                            # dashboard: 에이전트 복귀
                            if da:
                                dashboard_recall(da, f'✅ Complete ({elapsed:.1f}s)')

                        elif isinstance(text, str) and len(text) > 0:
                            summary = truncate(text, 100)
                            if len(text) > 200:
                                print(f"\033[90m[{fmt_time()}] [결과] {summary}\033[0m")
                            broadcaster.send(f"→ {truncate(text, 150)}")

            elif t == "result":
                cost = d.get("total_cost_usd", 0)
                dur = d.get("duration_ms", 0) / 1000
                turns = d.get("num_turns", 0)
                result_text = d.get("result", "")
                if len(result_text) > 100:
                    result_text = result_text[:100] + "..."

                print()
                print("\033[32m" + "━" * 55 + "\033[0m")
                print(f"\033[32m[{fmt_time()}] [SESSION END]\033[0m 💰 ${cost:.4f} | ⏱ {dur:.1f}초 | 🔄 {turns}턴")
                if result_text:
                    print(f"\033[32m[결과]\033[0m {result_text}")
                print("\033[32m" + "━" * 55 + "\033[0m")
                print()

                broadcaster.send(f"✨ *Session Complete* ${cost:.4f} {dur:.0f}s {turns}턴")
                dashboard_log('system', f'✨ Session complete (${cost:.4f})')

                # 모든 에이전트 복귀
                for agent_name in active_agents.values():
                    da = agent_name.get("dashboard_agent")
                    if da:
                        dashboard_recall(da, '✨ Session ended')
                active_agents.clear()

    except KeyboardInterrupt:
        print("\n\n종료.")

if __name__ == "__main__":
    main()
