#!/usr/bin/env python3
"""
🦑 SQUID TUI Monitor — curses 기반 채팅 + 에이전트 모니터 + 끼어들기

사용법:
    python3 scripts/tui_monitor.py
    bash scripts/monitor.sh

모드 (Tab/Shift+Tab 순환):
    Chat      — 텔레그램 채팅 인터페이스 (기본)
    Dashboard — 에이전트 상태 + 미션 로그
    Stream    — Raw Claude 이벤트 로그

Chat 모드:
    아무 문자  — 직접 타이핑
    Enter     — 메시지 전송
    Backspace — 마지막 문자 삭제
    Tab       — @멘션 자동완성 / 다음 모드
    Shift+Tab — 이전 모드
    Esc       — 입력 취소
    q         — 버퍼 비어있으면 종료
    /stop     — 작업 중단
    /resume   — executor 재시작

Dashboard/Stream 모드:
    :         — 커맨드 모드 진입
    q         — TUI 종료
    Tab       — 다음 모드
"""

import curses
import json
import os
import signal
import subprocess
import sys
import re
import time
import unicodedata
from collections import deque
from datetime import datetime

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from heysquid.core.agents import AGENTS, TOOL_EMOJI, SUBAGENT_MAP
from heysquid.core.config import get_env_path

# .env에서 BOT_TOKEN 로드
try:
    from dotenv import load_dotenv
    load_dotenv(get_env_path())
except ImportError:
    pass
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# --- 파일 경로 ---
STATUS_FILE = os.path.join(ROOT, "data", "agent_status.json")
STREAM_FILE = os.path.join(ROOT, "logs", "executor.stream.jsonl")
MESSAGES_FILE = os.path.join(ROOT, "data", "messages.json")
EXECUTOR_LOCK = os.path.join(ROOT, "data", "executor.lock")
EXECUTOR_SCRIPT = os.path.join(ROOT, "scripts", "executor.sh")
INTERRUPTED_FILE = os.path.join(ROOT, "data", "interrupted.json")
WORKING_LOCK_FILE = os.path.join(ROOT, "data", "working.json")

# --- 상수 ---
POLL_INTERVAL = 2.0  # 초
STREAM_BUFFER_SIZE = 200
CHAT_MAX_MESSAGES = 200
AGENT_ORDER = ["pm", "researcher", "developer", "reviewer", "tester", "writer"]
AGENT_SHORT = {"pm": "PM", "researcher": "researcher", "developer": "developer",
               "reviewer": "reviewer", "tester": "tester", "writer": "writer"}

# --- 모드 ---
MODE_CHAT = 0
MODE_DASHBOARD = 1
MODE_STREAM = 2
MODE_COUNT = 3
MODE_NAMES = {MODE_CHAT: "CHAT", MODE_DASHBOARD: "DASHBOARD", MODE_STREAM: "STREAM"}

# --- 채널 이모지 ---
CHANNEL_TAG = {
    "telegram": "[Telegram]",
    "tui": "[TUI]",
    "system": "[System]",
    "discord": "[Discord]",
    "slack": "[Slack]",
}

# --- 색상 매핑 (curses pair ID) ---
# pair 1~6: 에이전트, 7: 상태바, 8: dim, 9: 커맨드, 10: active, 11: commander
# 12: chat_user, 13: chat_bot, 14: chat_tui, 15: chat_date_sep
COLOR_PAIRS = {}


def _hex_to_curses_color(hex_color):
    """#rrggbb → curses 1000-scale RGB"""
    h = hex_color.lstrip("#")
    r = int(h[0:2], 16) * 1000 // 255
    g = int(h[2:4], 16) * 1000 // 255
    b = int(h[4:6], 16) * 1000 // 255
    return r, g, b


def init_colors():
    """curses 색상 초기화"""
    curses.start_color()
    curses.use_default_colors()

    if curses.can_change_color() and curses.COLORS >= 256:
        # 커스텀 색상 정의 (color 16+ 사용)
        for i, name in enumerate(AGENT_ORDER):
            color_id = 16 + i
            hex_c = AGENTS[name]["color_hex"]
            r, g, b = _hex_to_curses_color(hex_c)
            try:
                curses.init_color(color_id, r, g, b)
                curses.init_pair(i + 1, color_id, -1)
            except curses.error:
                curses.init_pair(i + 1, curses.COLOR_WHITE, -1)
            COLOR_PAIRS[name] = curses.color_pair(i + 1)
    else:
        # 256 미만: 고정 매핑
        fallback = {
            "pm": curses.COLOR_MAGENTA,
            "researcher": curses.COLOR_CYAN,
            "developer": curses.COLOR_YELLOW,
            "reviewer": curses.COLOR_GREEN,
            "tester": curses.COLOR_YELLOW,
            "writer": curses.COLOR_MAGENTA,
        }
        for i, name in enumerate(AGENT_ORDER):
            curses.init_pair(i + 1, fallback.get(name, curses.COLOR_WHITE), -1)
            COLOR_PAIRS[name] = curses.color_pair(i + 1)

    # 상태바: 반전
    curses.init_pair(7, curses.COLOR_BLACK, curses.COLOR_WHITE)
    # dim 텍스트
    curses.init_pair(8, curses.COLOR_WHITE, -1)
    # 커맨드 입력
    curses.init_pair(9, curses.COLOR_CYAN, -1)
    # active 상태 (녹색)
    curses.init_pair(10, curses.COLOR_GREEN, -1)
    # commander (흰색 bold)
    curses.init_pair(11, curses.COLOR_WHITE, -1)
    COLOR_PAIRS["commander"] = curses.color_pair(11) | curses.A_BOLD
    # chat: user 메시지 (기본색)
    curses.init_pair(12, curses.COLOR_WHITE, -1)
    # chat: bot 메시지 (PM 핑크 — fallback magenta)
    curses.init_pair(13, curses.COLOR_MAGENTA, -1)
    # chat: tui 메시지 (cyan dim)
    curses.init_pair(14, curses.COLOR_CYAN, -1)
    # chat: 날짜 구분선
    curses.init_pair(15, curses.COLOR_WHITE, -1)


# --- 유틸리티: 한글 폭 ---

def _display_width(text):
    """문자열의 터미널 표시 폭 계산 (한글=2칸, ASCII=1칸)"""
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def _wrap_text(text, max_width):
    """텍스트를 max_width에 맞춰 줄바꿈. 한글 2칸 폭 처리."""
    lines = []
    for raw_line in text.split('\n'):
        if not raw_line:
            lines.append("")
            continue
        current = ""
        current_w = 0
        for ch in raw_line:
            eaw = unicodedata.east_asian_width(ch)
            ch_w = 2 if eaw in ('W', 'F') else 1
            if current_w + ch_w > max_width:
                lines.append(current)
                current = ch
                current_w = ch_w
            else:
                current += ch
                current_w += ch_w
        if current:
            lines.append(current)
    return lines


def _get_at_context(cmd_buf):
    """현재 @멘션 입력 컨텍스트. (prefix, partial, candidates) or None."""
    at_pos = cmd_buf.rfind('@')
    if at_pos == -1:
        return None
    partial = cmd_buf[at_pos + 1:]
    if ' ' in partial:
        return None
    partial_lower = partial.lower()
    candidates = [a for a in AGENT_ORDER if a.startswith(partial_lower)]
    return (cmd_buf[:at_pos], partial, candidates) if candidates else None


def _parse_mentions(text):
    """텍스트에서 @agent 멘션 추출"""
    pattern = r'@(' + '|'.join(AGENT_ORDER) + r')\b'
    return re.findall(pattern, text, re.IGNORECASE)


# --- 데이터 로더 ---

def load_agent_status():
    """agent_status.json 로드"""
    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_stream_lines(last_pos, buffer):
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
        with open(STREAM_FILE, "r", encoding="utf-8") as f:
            f.seek(last_pos)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = _parse_stream_event(json.loads(line))
                    if parsed:
                        buffer.append(parsed)
                except json.JSONDecodeError:
                    pass
            return f.tell()
    except OSError:
        return last_pos


def _parse_stream_event(d):
    """JSONL 이벤트 → 표시용 (time, emoji, agent, text) 튜플"""
    t = d.get("type", "")
    now = datetime.now().strftime("%H:%M")

    if t == "system":
        subtype = d.get("subtype", "")
        if subtype == "init":
            model = d.get("model", "?")
            return (now, "🚀", "system", f"Session start ({model})")

    elif t == "assistant":
        content = d.get("message", {}).get("content", [])
        results = []
        for c in content:
            if c.get("type") == "text":
                text = c["text"].strip()
                if text:
                    results.append((now, "🦑", "pm", _trunc(text, 120)))
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
                    results.append((now, emoji, da or "pm",
                                    f"[{label}]{model_str} {desc}"))
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
                                    f"{name} → {_trunc(detail, 90)}"))
        return results[0] if results else None

    elif t == "result":
        cost = d.get("total_cost_usd", 0)
        dur = d.get("duration_ms", 0) / 1000
        turns = d.get("num_turns", 0)
        return (now, "✨", "system",
                f"Session end  ${cost:.4f} | {dur:.0f}s | {turns}턴")

    return None


def _trunc(text, maxlen=120):
    text = text.replace("\n", " ").strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


# --- Chat 데이터 폴링 ---

_chat_cache = {"mtime": 0, "messages": []}


def _poll_chat_messages():
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
        # user + bot 메시지만 (최근 CHAT_MAX_MESSAGES개)
        chat_msgs = [m for m in msgs if m.get("type") in ("user", "bot")]
        chat_msgs = chat_msgs[-CHAT_MAX_MESSAGES:]
        _chat_cache["mtime"] = mtime
        _chat_cache["messages"] = chat_msgs
    except (json.JSONDecodeError, OSError):
        pass

    return _chat_cache["messages"]


# --- Chat 메시지 → 렌더링 라인 변환 ---

def _messages_to_lines(messages, content_width):
    """메시지 리스트 → (text, attr) 튜플 리스트로 변환. 날짜 구분선 포함."""
    lines = []
    last_date = None

    for msg in messages:
        ts = msg.get("timestamp", "")
        msg_type = msg.get("type", "")
        text = msg.get("text", "")
        channel = msg.get("channel", msg.get("source", "telegram"))

        # 날짜 파싱
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            date_str = dt.strftime("%Y/%m/%d")
            time_str = dt.strftime("%H:%M")
        except (ValueError, TypeError):
            date_str = ""
            time_str = "??:??"

        # 날짜 구분선
        if date_str and date_str != last_date:
            last_date = date_str
            sep = f"── {date_str} ──"
            lines.append(("", 0))  # 빈줄
            lines.append((sep, "date_sep"))
            lines.append(("", 0))

        # 발신자 헤더 (색상) + 본문 (기본색) 분리
        ch_tag = CHANNEL_TAG.get(channel, f"[{channel}]")
        if msg_type == "user":
            source = msg.get("source", channel)
            if source == "tui":
                sender = f"[{time_str}] {ch_tag} COMMANDER"
                header_key = "tui"
                body_key = "tui_body"
            else:
                name = msg.get("first_name") or msg.get("username") or "User"
                sender = f"[{time_str}] {ch_tag} {name}"
                header_key = "user"
                body_key = "body"
        else:
            sender = f"[{time_str}] SQUID 🦑"
            header_key = "bot"
            body_key = "body"

        lines.append((sender, header_key))

        # 메시지 본문 줄바꿈 (기본색)
        if text:
            wrapped = _wrap_text(text, content_width - 2)
            for wl in wrapped:
                lines.append((f"  {wl}", body_key))

        # 파일 첨부 표시
        files = msg.get("files", [])
        if files:
            for fi in files:
                fname = fi.get("name") or fi.get("type", "file")
                lines.append((f"  📎 {fname}", body_key))

        lines.append(("", 0))  # 메시지 간 간격

    return lines


# --- 메시지 주입 ---

def _get_real_user_info(messages):
    """기존 텔레그램 메시지에서 실제 사용자 정보 조회"""
    for msg in reversed(messages):
        cid = msg.get("chat_id", 0)
        uid = msg.get("user_id", 0)
        if isinstance(cid, int) and cid > 0 and msg.get("source") != "tui":
            return {
                "chat_id": cid,
                "user_id": uid,
                "username": msg.get("username", "tui"),
                "first_name": msg.get("first_name", "TUI"),
            }
    return None


def inject_local_message(text):
    """messages.json에 TUI 메시지 주입.
    음수 message_id, source: tui, channel: tui, processed: False.
    실제 chat_id를 사용하여 PM이 텔레그램으로 답장 가능."""
    os.makedirs(os.path.dirname(MESSAGES_FILE), exist_ok=True)

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"messages": [], "last_update_id": 0}

    user_info = _get_real_user_info(data.get("messages", []))

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
        "files": [],
        "location": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processed": False,
        "source": "tui",
        "mentions": _parse_mentions(text),
    }

    data["messages"].append(message)

    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 텔레그램에 포워딩
    chat_id = user_info["chat_id"] if user_info else 0
    if chat_id:
        _forward_to_telegram(chat_id, text)

    return new_id


def _forward_to_telegram(chat_id, text):
    """TUI 메시지를 텔레그램 채팅에 포워딩 (curl subprocess)"""
    if not BOT_TOKEN or not chat_id:
        return
    tg_text = f"[TUI] COMMANDER: {text}"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": tg_text})
    try:
        subprocess.Popen(
            ["curl", "-s", "-X", "POST", url,
             "-H", "Content-Type: application/json",
             "-d", payload],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # 포워딩 실패해도 메시지 전송 자체는 성공


def _kill_executor():
    """executor Claude 프로세스 종료"""
    killed = False

    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude.*append-system-prompt-file"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            for pid in result.stdout.strip().split("\n"):
                pid = pid.strip()
                if pid:
                    subprocess.run(["kill", pid], capture_output=True)
                    killed = True
    except Exception:
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

    return killed


def _resume_executor():
    """executor.sh 백그라운드 실행"""
    if os.path.exists(EXECUTOR_LOCK):
        return False, "executor 이미 실행 중"

    if not os.path.exists(EXECUTOR_SCRIPT):
        return False, "executor.sh 없음"

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
    return True, "executor 시작됨"


def _log_commander_message(text, stream_buffer):
    """TUI 커맨더 메시지를 로그에 기록 (Stream + Dashboard 양쪽)"""
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


# --- TUI 렌더링 ---

def _safe_addstr(win, y, x, text, attr=0, max_x=None):
    """curses addstr wrapper — 화면 밖 쓰기 방지"""
    h, w = win.getmaxyx()
    if max_x is not None:
        w = min(w, max_x)
    if y < 0 or y >= h or x >= w:
        return
    avail = w - x - 1
    if avail <= 0:
        return
    text = str(text)[:avail]
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def _render_agent_compact_bar(win, row, status):
    """에이전트 상태 1줄 compact 바 (Chat 모드 row 1)"""
    h, w = win.getmaxyx()
    x = 1
    for name in AGENT_ORDER:
        if name == "pm":
            continue  # PM은 타이틀에 이미 표시
        info = AGENTS.get(name, {})
        emoji = info.get("emoji", "🤖")
        color = COLOR_PAIRS.get(name, curses.A_NORMAL)

        agent_data = status.get(name, {})
        agent_st = agent_data.get("status", "idle")

        if agent_st == "idle":
            label = f"{emoji}idle"
            attr = curses.A_DIM
        else:
            label = f"{emoji}{agent_st[:4]}"
            attr = color | curses.A_BOLD

        _safe_addstr(win, row, x, label, attr)
        x += len(label) + 2
        if x >= w - 5:
            break


def render_chat(win, chat_lines, input_buf, flash_msg, status):
    """Chat 모드 렌더링"""
    h, w = win.getmaxyx()
    if h < 6 or w < 30:
        _safe_addstr(win, 0, 0, "Terminal too small")
        return

    now = datetime.now().strftime("%H:%M:%S")
    is_live = os.path.exists(EXECUTOR_LOCK)
    indicator = "● LIVE" if is_live else "○ IDLE"

    # row 0: 타이틀
    _safe_addstr(win, 0, 1, "🦑 SQUID", curses.A_BOLD)
    _safe_addstr(win, 0, 11, "[CHAT]",
                 COLOR_PAIRS.get("pm", curses.A_NORMAL) | curses.A_BOLD)
    right_info = f"{indicator}  {now}"
    _safe_addstr(win, 0, w - len(right_info) - 2, right_info,
                 curses.color_pair(10) | curses.A_BOLD if is_live else curses.A_DIM)

    # row 1: 에이전트 상태 compact
    _render_agent_compact_bar(win, 1, status)

    # row 2: 구분선
    _safe_addstr(win, 2, 0, "─" * (w - 1))

    # 채팅 영역: row 3 ~ h-3
    chat_top = 3
    chat_bottom = h - 3  # h-2 = 입력줄, h-1 = 상태바
    chat_rows = chat_bottom - chat_top

    if chat_rows > 0 and chat_lines:
        # 최신 메시지가 하단에 오도록 (auto-scroll)
        visible = chat_lines[-chat_rows:] if len(chat_lines) > chat_rows else chat_lines
        start_row = chat_bottom - len(visible)

        for i, (text, attr_key) in enumerate(visible):
            row = start_row + i
            if row < chat_top or row >= chat_bottom:
                continue

            if attr_key == "date_sep":
                attr = curses.color_pair(15) | curses.A_DIM
                pad = (w - _display_width(text)) // 2
                if pad < 1:
                    pad = 1
                _safe_addstr(win, row, pad, text, attr)
            elif attr_key == "user":
                # 사용자 헤더: 흰색 bold
                _safe_addstr(win, row, 1, text,
                             curses.color_pair(12) | curses.A_BOLD)
            elif attr_key == "bot":
                # PM 헤더: PM 색상 (핑크)
                _safe_addstr(win, row, 1, text,
                             COLOR_PAIRS.get("pm", curses.color_pair(13)))
            elif attr_key == "tui":
                # COMMANDER 헤더: cyan (bold 없이)
                _safe_addstr(win, row, 1, text, curses.color_pair(14))
            elif attr_key == "body":
                # 본문: 기본색
                _safe_addstr(win, row, 1, text, curses.A_NORMAL)
            elif attr_key == "tui_body":
                # COMMANDER 본문: 기본색 (잘 보이게)
                _safe_addstr(win, row, 1, text, curses.A_NORMAL)
            elif isinstance(attr_key, int):
                _safe_addstr(win, row, 1, text, attr_key)
            else:
                _safe_addstr(win, row, 1, text, curses.A_NORMAL)

    # h-3: 구분선
    _safe_addstr(win, h - 3, 0, "─" * (w - 1))

    # h-2: 입력줄
    prompt = f"> {input_buf}"
    if not input_buf:
        _safe_addstr(win, h - 2, 1, "> ", curses.color_pair(14))
        _safe_addstr(win, h - 2, 3, "메시지 입력...", curses.A_DIM)
    else:
        _safe_addstr(win, h - 2, 1, prompt, curses.color_pair(14))

    # @멘션 힌트
    at_ctx = _get_at_context(input_buf)
    if at_ctx:
        _, partial, candidates = at_ctx
        hint_x = 1 + _display_width(prompt) + 2
        for name in candidates[:3]:
            emoji = AGENTS[name]["emoji"]
            label = f"{emoji}@{name}"
            color = COLOR_PAIRS.get(name, curses.A_NORMAL) | curses.A_BOLD
            _safe_addstr(win, h - 2, hint_x, label, color)
            hint_x += len(label) + 1

    # h-1: 상태바
    bar_left = " q:quit  Tab:mode  Enter:send"
    if flash_msg:
        bar_left += f"  {flash_msg}"
    bar_right = " @agent:Tab완성 "
    padding = w - len(bar_left) - len(bar_right)
    if padding > 0:
        bar = bar_left + " " * padding + bar_right
    else:
        bar = bar_left
    _safe_addstr(win, h - 1, 0, bar[:w - 1],
                 curses.color_pair(7) | curses.A_BOLD)


def render_dashboard(win, status):
    """Dashboard 모드 렌더링"""
    h, w = win.getmaxyx()
    if h < 10 or w < 40:
        _safe_addstr(win, 0, 0, "Terminal too small")
        return

    quest = status.get("current_task", "")
    _safe_addstr(win, 0, 1, "🦑 SQUID Agent Monitor", curses.A_BOLD)
    _safe_addstr(win, 0, 25, "[DASHBOARD]",
                 COLOR_PAIRS.get("pm", curses.A_NORMAL) | curses.A_BOLD)

    if quest:
        _safe_addstr(win, 1, 1, f"Quest: {_trunc(quest, w - 12)}", curses.A_DIM)

    _safe_addstr(win, 2, 0, "─" * (w - 1))

    left_w = 18
    sep_x = left_w

    _safe_addstr(win, 3, 1, "AGENTS", curses.A_BOLD)

    for row in range(3, h - 2):
        _safe_addstr(win, row, sep_x, "│")

    _safe_addstr(win, 3, sep_x + 2, "SQUID LOG", curses.A_BOLD)

    row = 5
    for agent_name in AGENT_ORDER:
        if row >= h - 3:
            break
        info = AGENTS.get(agent_name, {})
        emoji = info.get("emoji", "🤖")
        short = AGENT_SHORT.get(agent_name, agent_name[:3])
        color = COLOR_PAIRS.get(agent_name, curses.A_NORMAL)

        agent_data = status.get(agent_name, {})
        agent_status = agent_data.get("status", "idle")
        task = agent_data.get("task", "")

        _safe_addstr(win, row, 1, f"{emoji} {short}", color | curses.A_BOLD)
        row += 1

        if agent_status == "idle":
            _safe_addstr(win, row, 3, "idle", curses.A_DIM)
        else:
            status_str = f"▶ {_trunc(task, left_w - 5)}" if task else f"▶ {agent_status}"
            _safe_addstr(win, row, 3, status_str, curses.color_pair(10))
        row += 2

    logs = status.get("mission_log", [])
    log_start_row = 5
    max_log_rows = h - log_start_row - 2
    right_x = sep_x + 2
    right_w = w - right_x - 1

    visible_logs = logs[-max_log_rows:] if len(logs) > max_log_rows else logs
    visible_logs = list(reversed(visible_logs))

    for i, entry in enumerate(visible_logs):
        if i >= max_log_rows:
            break
        t = entry.get("time", "")
        agent = entry.get("agent", "")
        msg = entry.get("message", "")

        emoji = ""
        color = curses.A_NORMAL
        if agent in AGENTS:
            emoji = AGENTS[agent]["emoji"]
            color = COLOR_PAIRS.get(agent, curses.A_NORMAL)
        elif agent == "commander":
            emoji = "🎖️"
            color = COLOR_PAIRS.get("commander", curses.A_BOLD)
        elif agent == "system":
            emoji = "⚙️"

        line = f"{t} {emoji} {msg}"
        _safe_addstr(win, log_start_row + i, right_x, _trunc(line, right_w),
                     color if i == 0 else curses.A_DIM)


def render_stream(win, stream_buffer):
    """Stream 모드 렌더링"""
    h, w = win.getmaxyx()
    if h < 5 or w < 40:
        _safe_addstr(win, 0, 0, "Terminal too small")
        return

    _safe_addstr(win, 0, 1, "🦑 SQUID Stream Log", curses.A_BOLD)
    _safe_addstr(win, 0, 22, "[STREAM]",
                 COLOR_PAIRS.get("pm", curses.A_NORMAL) | curses.A_BOLD)

    _safe_addstr(win, 1, 0, "─" * (w - 1))

    max_rows = h - 4
    visible = list(stream_buffer)[-max_rows:] if len(stream_buffer) > max_rows else list(stream_buffer)
    visible = list(reversed(visible))

    for i, entry in enumerate(visible):
        if i >= max_rows:
            break
        tm, emoji, agent, text = entry
        color = COLOR_PAIRS.get(agent, curses.A_NORMAL)

        line = f"[{tm}] {emoji} {text}"
        attr = color if i == 0 else curses.A_DIM
        _safe_addstr(win, 2 + i, 1, _trunc(line, w - 3), attr)


def render_status_bar_legacy(win, mode, cmd_mode, cmd_buf, flash_msg):
    """하단 상태바 (Dashboard/Stream 모드용)"""
    h, w = win.getmaxyx()

    if cmd_mode:
        at_ctx = _get_at_context(cmd_buf)
        if at_ctx and h > 3:
            _, partial, candidates = at_ctx
            x = 1
            for name in AGENT_ORDER:
                emoji = AGENTS[name]["emoji"]
                label = f"{emoji}@{name}"
                is_match = name in candidates
                color = (COLOR_PAIRS.get(name, curses.A_NORMAL) | curses.A_BOLD) if is_match else curses.A_DIM
                _safe_addstr(win, h - 2, x, label, color)
                x += len(label) + 2

        _safe_addstr(win, h - 1, 0, " " * (w - 1), curses.color_pair(9))
        prompt = f": {cmd_buf}"
        _safe_addstr(win, h - 1, 1, prompt, curses.color_pair(9) | curses.A_BOLD)
    else:
        now = datetime.now().strftime("%H:%M:%S")
        is_live = os.path.exists(EXECUTOR_LOCK)
        indicator = "● LIVE" if is_live else "○ IDLE"

        bar = f" {now} {indicator}"
        help_text = "q:quit Tab:mode :cmd"
        if flash_msg:
            bar += f"  {flash_msg}"
        padding = w - len(bar) - len(help_text) - 2
        if padding > 0:
            bar += " " * padding
        bar += help_text + " "

        attr = curses.color_pair(7) | curses.A_BOLD
        _safe_addstr(win, h - 1, 0, bar[:w - 1], attr)


# --- Chat 메시지 전송 ---

def _send_chat_message(text, stream_buffer):
    """Chat 모드에서 메시지 전송 처리. flash 메시지 반환."""
    text = text.strip()
    if not text:
        return ""

    # 특수 명령
    if text == "/stop":
        killed = _kill_executor()
        return "작업 중단됨" if killed else "실행 중인 작업 없음"

    if text == "/resume":
        ok, msg = _resume_executor()
        return msg

    # 일반 메시지
    mid = inject_local_message(text)
    mentions = _parse_mentions(text)
    _log_commander_message(text, stream_buffer)

    if not os.path.exists(EXECUTOR_LOCK):
        _resume_executor()

    if mentions:
        return f"→ {' '.join('@' + m for m in mentions)}"
    return ""


# --- 커맨드 실행 (Dashboard/Stream) ---

def _execute_command(cmd, stream_buffer):
    """커맨드 파싱 및 실행 (: 접두사 모드)"""
    cmd = cmd.strip()
    if not cmd:
        return ""

    if cmd == "stop":
        killed = _kill_executor()
        return "작업 중단됨" if killed else "실행 중인 작업 없음"

    elif cmd == "resume":
        ok, msg = _resume_executor()
        return msg

    elif cmd.startswith("msg "):
        text = cmd[4:].strip()
        if text:
            mid = inject_local_message(text)
            mentions = _parse_mentions(text)
            _log_commander_message(text, stream_buffer)
            if not os.path.exists(EXECUTOR_LOCK):
                _resume_executor()
            if mentions:
                return f"→ {' '.join('@' + m for m in mentions)} (id={mid})"
            return f"메시지 전송 (id={mid})"
        return "텍스트를 입력하세요"

    else:
        mid = inject_local_message(cmd)
        mentions = _parse_mentions(cmd)
        _log_commander_message(cmd, stream_buffer)
        if not os.path.exists(EXECUTOR_LOCK):
            _resume_executor()
        if mentions:
            return f"→ {' '.join('@' + m for m in mentions)} (id={mid})"
        return f"메시지 전송 (id={mid})"


# --- 메인 루프 ---

def tui_main(stdscr):
    """curses TUI 메인 루프"""
    curses.curs_set(0)
    stdscr.timeout(int(POLL_INTERVAL * 1000))
    stdscr.keypad(True)
    init_colors()

    mode = MODE_CHAT  # 기본 모드: Chat
    cmd_mode = False  # Dashboard/Stream의 : 커맨드 모드
    cmd_buf = ""
    chat_buf = ""  # Chat 모드 입력 버퍼
    flash_msg = ""
    flash_expire = 0
    tab_index = 0

    stream_buffer = deque(maxlen=STREAM_BUFFER_SIZE)
    stream_pos = 0

    def handle_resize(sig, frame):
        curses.endwin()
        stdscr.refresh()
    signal.signal(signal.SIGWINCH, handle_resize)

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()

        # flash 메시지 타임아웃
        if flash_msg and time.time() > flash_expire:
            flash_msg = ""

        # 데이터 로드 + 렌더링
        if mode == MODE_CHAT:
            messages = _poll_chat_messages()
            status = load_agent_status()
            content_width = w - 4
            chat_lines = _messages_to_lines(messages, content_width)
            render_chat(stdscr, chat_lines, chat_buf, flash_msg, status)
            # Chat 모드는 입력줄에 커서
            if chat_buf:
                curses.curs_set(1)
            else:
                curses.curs_set(0)

        elif mode == MODE_DASHBOARD:
            status = load_agent_status()
            render_dashboard(stdscr, status)
            if h > 2:
                _safe_addstr(stdscr, h - 2, 0, "─" * (w - 1))
            render_status_bar_legacy(stdscr, mode, cmd_mode, cmd_buf, flash_msg)
            if cmd_mode:
                curses.curs_set(1)
            else:
                curses.curs_set(0)

        else:  # MODE_STREAM
            stream_pos = load_stream_lines(stream_pos, stream_buffer)
            render_stream(stdscr, stream_buffer)
            if h > 2:
                _safe_addstr(stdscr, h - 2, 0, "─" * (w - 1))
            render_status_bar_legacy(stdscr, mode, cmd_mode, cmd_buf, flash_msg)
            if cmd_mode:
                curses.curs_set(1)
            else:
                curses.curs_set(0)

        stdscr.refresh()

        # --- 입력 처리 ---
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue

        is_char = isinstance(ch, str)
        ch_ord = ord(ch) if is_char else ch

        if mode == MODE_CHAT:
            # --- Chat 모드 입력 ---
            if ch_ord == 27:  # Esc
                chat_buf = ""
                tab_index = 0
            elif ch_ord == 9:  # Tab
                at_ctx = _get_at_context(chat_buf)
                if at_ctx:
                    # @멘션 자동완성
                    prefix, partial, candidates = at_ctx
                    if candidates:
                        selected = candidates[tab_index % len(candidates)]
                        chat_buf = prefix + '@' + selected + ' '
                        tab_index += 1
                else:
                    # 다음 모드
                    mode = MODE_DASHBOARD
                    chat_buf = ""
                    tab_index = 0
            elif ch_ord == curses.KEY_BTAB:  # Shift+Tab
                mode = MODE_STREAM
                chat_buf = ""
                tab_index = 0
            elif ch_ord in (curses.KEY_ENTER, 10, 13):
                # 붙여넣기 감지: Enter 후 즉시 입력이 오면 줄바꿈→공백
                stdscr.nodelay(True)
                paste_chars = []
                try:
                    while True:
                        try:
                            nch = stdscr.get_wch()
                            nch_is_char = isinstance(nch, str)
                            nch_ord = ord(nch) if nch_is_char else nch
                            if nch_ord in (curses.KEY_ENTER, 10, 13):
                                paste_chars.append(' ')
                            elif nch_is_char and nch_ord >= 32:
                                paste_chars.append(nch)
                            elif nch_ord in (curses.KEY_BACKSPACE, 127, 8):
                                pass  # 무시
                        except curses.error:
                            break  # 더 이상 입력 없음
                finally:
                    stdscr.nodelay(False)
                    stdscr.timeout(int(POLL_INTERVAL * 1000))

                if paste_chars:
                    # 붙여넣기 모드: 버퍼에 추가
                    chat_buf += ' ' + ''.join(paste_chars)
                else:
                    # 일반 Enter: 메시지 전송
                    if chat_buf.strip():
                        result = _send_chat_message(chat_buf, stream_buffer)
                        if result:
                            flash_msg = result
                            flash_expire = time.time() + 5
                        _chat_cache["mtime"] = 0
                    chat_buf = ""
                tab_index = 0
            elif ch_ord in (curses.KEY_BACKSPACE, 127, 8):
                chat_buf = chat_buf[:-1]
                tab_index = 0
            elif is_char and ch_ord >= 32:
                # q: 버퍼 비어있으면 종료, 아니면 일반 문자
                if ch == 'q' and not chat_buf:
                    break
                chat_buf += ch
                tab_index = 0

        elif cmd_mode:
            # --- Dashboard/Stream : 커맨드 모드 ---
            if ch_ord == 27:  # Esc
                cmd_mode = False
                cmd_buf = ""
                tab_index = 0
            elif ch_ord == 9:  # Tab — @멘션 자동완성
                at_ctx = _get_at_context(cmd_buf)
                if at_ctx:
                    prefix, partial, candidates = at_ctx
                    if candidates:
                        selected = candidates[tab_index % len(candidates)]
                        cmd_buf = prefix + '@' + selected
                        tab_index += 1
            elif ch_ord in (curses.KEY_ENTER, 10, 13):
                result = _execute_command(cmd_buf, stream_buffer)
                flash_msg = result
                flash_expire = time.time() + 5
                cmd_mode = False
                cmd_buf = ""
                tab_index = 0
            elif ch_ord in (curses.KEY_BACKSPACE, 127, 8):
                cmd_buf = cmd_buf[:-1]
                tab_index = 0
            elif is_char and ch_ord >= 32:
                cmd_buf += ch
                tab_index = 0

        else:
            # --- Dashboard/Stream 일반 모드 ---
            if is_char and ch == "q":
                break
            elif ch_ord == 9:  # Tab → 다음 모드
                mode = (mode + 1) % MODE_COUNT
            elif ch_ord == curses.KEY_BTAB:  # Shift+Tab → 이전 모드
                mode = (mode - 1) % MODE_COUNT
            elif is_char and ch == ":":
                cmd_mode = True
                cmd_buf = ""


# --- 엔트리포인트 ---

if __name__ == "__main__":
    try:
        curses.wrapper(tui_main)
    except KeyboardInterrupt:
        pass
