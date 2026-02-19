#!/usr/bin/env python3
"""
🦑 SQUID TUI Monitor — curses 기반 에이전트 모니터 + 끼어들기

사용법:
    python3 scripts/tui_monitor.py
    bash scripts/monitor.sh

키 조작:
    Tab   — Dashboard ↔ Stream 모드 전환
    :     — 커맨드 모드 진입
    Enter — 커맨드 실행
    Esc   — 커맨드 모드 취소
    q     — TUI 종료

커맨드:
    :stop           — 현재 작업 중단
    :resume         — executor.sh 백그라운드 실행
    :msg <텍스트>    — PM에게 메시지 전송
    :<아무 텍스트>   — = :msg <텍스트>
"""

import curses
import json
import os
import signal
import subprocess
import sys
import time
from collections import deque
from datetime import datetime

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from heysquid.core.agents import AGENTS, TOOL_EMOJI, SUBAGENT_MAP

# --- 파일 경로 ---
STATUS_FILE = os.path.join(ROOT, "data", "agent_status.json")
STREAM_FILE = os.path.join(ROOT, "logs", "executor.stream.jsonl")
MESSAGES_FILE = os.path.join(ROOT, "data", "telegram_messages.json")
EXECUTOR_LOCK = os.path.join(ROOT, "data", "executor.lock")
EXECUTOR_SCRIPT = os.path.join(ROOT, "scripts", "executor.sh")
INTERRUPTED_FILE = os.path.join(ROOT, "data", "interrupted.json")
WORKING_LOCK_FILE = os.path.join(ROOT, "data", "working.json")

# --- 상수 ---
POLL_INTERVAL = 2.0  # 초
STREAM_BUFFER_SIZE = 200
AGENT_ORDER = ["pm", "researcher", "developer", "reviewer", "tester", "writer"]
AGENT_SHORT = {"pm": "PM", "researcher": "researcher", "developer": "developer",
               "reviewer": "reviewer", "tester": "tester", "writer": "writer"}

MODE_DASHBOARD = 0
MODE_STREAM = 1
MODE_NAMES = {MODE_DASHBOARD: "DASHBOARD", MODE_STREAM: "LOG"}

# --- 색상 매핑 (curses pair ID) ---
# pair 1~6: 에이전트, 7: 상태바, 8: dim, 9: 커맨드
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
        # 파일이 truncate됨 (새 세션)
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
        # 여러 결과가 있으면 첫 번째만 (너무 길어지니까)
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


# --- 메시지 주입 ---

def inject_local_message(text):
    """telegram_messages.json에 TUI 메시지 주입.
    음수 message_id, source: tui, processed: False.
    PM이 poll_new_messages()로 자동 픽업."""
    os.makedirs(os.path.dirname(MESSAGES_FILE), exist_ok=True)

    try:
        with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {"messages": [], "last_update_id": 0}

    # 음수 message_id 생성 (기존 TUI 메시지와 충돌 방지)
    tui_ids = [
        m["message_id"] for m in data.get("messages", [])
        if isinstance(m.get("message_id"), int) and m["message_id"] < 0
    ]
    new_id = min(tui_ids) - 1 if tui_ids else -1

    message = {
        "message_id": new_id,
        "type": "user",
        "user_id": 0,
        "username": "tui",
        "first_name": "TUI",
        "last_name": "",
        "chat_id": 0,
        "text": text,
        "files": [],
        "location": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "processed": False,
        "source": "tui",
    }

    data["messages"].append(message)

    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return new_id


def _kill_executor():
    """executor Claude 프로세스 종료 (listener의 _kill_executor 로직 재현)"""
    killed = False

    # Claude executor 프로세스 kill
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

    # executor.lock 삭제
    try:
        if os.path.exists(EXECUTOR_LOCK):
            os.remove(EXECUTOR_LOCK)
    except OSError:
        pass

    # working.json 읽고 삭제
    working_info = None
    try:
        if os.path.exists(WORKING_LOCK_FILE):
            with open(WORKING_LOCK_FILE, "r", encoding="utf-8") as f:
                working_info = json.load(f)
            os.remove(WORKING_LOCK_FILE)
    except Exception:
        pass

    # interrupted.json 저장
    interrupted_data = {
        "interrupted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "reason": "TUI :stop",
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


def render_dashboard(win, status):
    """Dashboard 모드 렌더링"""
    h, w = win.getmaxyx()
    if h < 10 or w < 40:
        _safe_addstr(win, 0, 0, "Terminal too small")
        return

    # 제목
    quest = status.get("current_task", "")
    _safe_addstr(win, 0, 1, "🦑 SQUID Agent Monitor", curses.A_BOLD)
    mode_tag = f"[Tab: {MODE_NAMES[MODE_STREAM]}]"
    _safe_addstr(win, 0, w - len(mode_tag) - 2, mode_tag, curses.A_DIM)

    if quest:
        _safe_addstr(win, 1, 1, f"Quest: {_trunc(quest, w - 12)}", curses.A_DIM)

    # 구분선
    _safe_addstr(win, 2, 0, "─" * (w - 1))

    # 레이아웃: 왼쪽 에이전트 (18칸) | 오른쪽 미션 로그
    left_w = 18
    sep_x = left_w

    # 왼쪽 헤더
    _safe_addstr(win, 3, 1, "AGENTS", curses.A_BOLD)

    # 구분선 세로
    for row in range(3, h - 2):
        _safe_addstr(win, row, sep_x, "│")

    # 오른쪽 헤더
    _safe_addstr(win, 3, sep_x + 2, "MISSION LOG", curses.A_BOLD)

    # 에이전트 목록
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

    # 미션 로그
    logs = status.get("mission_log", [])
    log_start_row = 5
    max_log_rows = h - log_start_row - 2
    right_x = sep_x + 2
    right_w = w - right_x - 1

    # 최신 순으로 표시
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
    mode_tag = f"[Tab: {MODE_NAMES[MODE_DASHBOARD]}]"
    _safe_addstr(win, 0, w - len(mode_tag) - 2, mode_tag, curses.A_DIM)

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


def render_status_bar(win, mode, cmd_mode, cmd_buf, flash_msg):
    """하단 상태바"""
    h, w = win.getmaxyx()

    if cmd_mode:
        # 커맨드 입력
        _safe_addstr(win, h - 1, 0, " " * (w - 1), curses.color_pair(9))
        prompt = f": {cmd_buf}"
        _safe_addstr(win, h - 1, 1, prompt, curses.color_pair(9) | curses.A_BOLD)
    else:
        now = datetime.now().strftime("%H:%M:%S")

        # executor 상태
        is_live = os.path.exists(EXECUTOR_LOCK)
        indicator = "● LIVE" if is_live else "○ IDLE"

        bar = f" {now} {indicator}"
        help_text = "q:quit Tab:mode :command"
        if flash_msg:
            bar += f"  {flash_msg}"
        padding = w - len(bar) - len(help_text) - 2
        if padding > 0:
            bar += " " * padding
        bar += help_text + " "

        attr = curses.color_pair(7) | curses.A_BOLD
        _safe_addstr(win, h - 1, 0, bar[:w - 1], attr)


# --- 메인 루프 ---

def tui_main(stdscr):
    """curses TUI メインループ"""
    curses.curs_set(0)
    stdscr.timeout(int(POLL_INTERVAL * 1000))
    stdscr.keypad(True)
    init_colors()

    mode = MODE_DASHBOARD
    cmd_mode = False
    cmd_buf = ""
    flash_msg = ""
    flash_expire = 0

    stream_buffer = deque(maxlen=STREAM_BUFFER_SIZE)
    stream_pos = 0

    # SIGWINCH はcursesが自動処理するがリフレッシュが必要
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

        # 데이터 로드
        if mode == MODE_DASHBOARD:
            status = load_agent_status()
            render_dashboard(stdscr, status)
        else:
            stream_pos = load_stream_lines(stream_pos, stream_buffer)
            render_stream(stdscr, stream_buffer)

        # 구분선 (상태바 위)
        if h > 2:
            _safe_addstr(stdscr, h - 2, 0, "─" * (w - 1))

        render_status_bar(stdscr, mode, cmd_mode, cmd_buf, flash_msg)
        stdscr.refresh()

        # 입력 처리 — get_wch()로 한글 등 wide char 지원
        try:
            ch = stdscr.get_wch()
        except curses.error:
            continue

        # get_wch(): str이면 일반 문자, int이면 특수키, timeout이면 error
        is_char = isinstance(ch, str)
        ch_ord = ord(ch) if is_char else ch

        if cmd_mode:
            if ch_ord == 27:  # Esc
                cmd_mode = False
                cmd_buf = ""
            elif ch_ord in (curses.KEY_ENTER, 10, 13):
                # 커맨드 실행
                result = _execute_command(cmd_buf, stream_buffer)
                flash_msg = result
                flash_expire = time.time() + 5
                cmd_mode = False
                cmd_buf = ""
            elif ch_ord in (curses.KEY_BACKSPACE, 127, 8):
                cmd_buf = cmd_buf[:-1]
            elif is_char and ch_ord >= 32:
                # ASCII + 한글 + 이모지 등 모든 printable 문자
                cmd_buf += ch
        else:
            if is_char and ch == "q":
                break
            elif ch_ord == 9:  # Tab
                mode = MODE_STREAM if mode == MODE_DASHBOARD else MODE_DASHBOARD
            elif is_char and ch == ":":
                cmd_mode = True
                cmd_buf = ""
                curses.curs_set(1)

        if not cmd_mode:
            curses.curs_set(0)


def _execute_command(cmd, stream_buffer):
    """커맨드 파싱 및 실행"""
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
            # PM이 없으면 executor 트리거
            if not os.path.exists(EXECUTOR_LOCK):
                _resume_executor()
            return f"메시지 전송 (id={mid})"
        return "텍스트를 입력하세요"

    else:
        # 자유 텍스트 = :msg 축약
        mid = inject_local_message(cmd)
        if not os.path.exists(EXECUTOR_LOCK):
            _resume_executor()
        return f"메시지 전송 (id={mid})"


# --- 엔트리포인트 ---

if __name__ == "__main__":
    try:
        curses.wrapper(tui_main)
    except KeyboardInterrupt:
        pass
