"""유틸리티 — 한글 폭 계산, 줄바꿈, 텍스트 자르기"""

import re
import unicodedata

# tui_monitor.py에서 사용하는 에이전트 순서
AGENT_ORDER = ["pm", "researcher", "developer", "reviewer", "tester", "writer"]
AGENT_SHORT = {
    "pm": "PM", "researcher": "researcher", "developer": "developer",
    "reviewer": "reviewer", "tester": "tester", "writer": "writer",
}


def display_width(text: str) -> int:
    """문자열의 터미널 표시 폭 계산 (한글=2칸, ASCII=1칸)"""
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def wrap_text(text: str, max_width: int) -> list[str]:
    """텍스트를 max_width에 맞춰 줄바꿈. 한글 2칸 폭 처리."""
    lines = []
    for raw_line in text.split("\n"):
        if not raw_line:
            lines.append("")
            continue
        current = ""
        current_w = 0
        for ch in raw_line:
            eaw = unicodedata.east_asian_width(ch)
            ch_w = 2 if eaw in ("W", "F") else 1
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


def trunc(text: str, maxlen: int = 120) -> str:
    """텍스트를 maxlen으로 자르기 (줄바꿈 제거)"""
    text = text.replace("\n", " ").strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


def get_at_context(cmd_buf: str):
    """현재 @멘션 입력 컨텍스트. (prefix, partial, candidates) or None."""
    at_pos = cmd_buf.rfind("@")
    if at_pos == -1:
        return None
    partial = cmd_buf[at_pos + 1:]
    if " " in partial:
        return None
    partial_lower = partial.lower()
    candidates = [a for a in AGENT_ORDER if a.startswith(partial_lower)]
    return (cmd_buf[:at_pos], partial, candidates) if candidates else None


def parse_mentions(text: str) -> list[str]:
    """텍스트에서 @agent 멘션 추출"""
    pattern = r"@(" + "|".join(AGENT_ORDER) + r")\b"
    return re.findall(pattern, text, re.IGNORECASE)
