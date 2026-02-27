"""Utilities -- CJK character width calculation, line wrapping, text truncation."""

import re
import unicodedata

# Agent order used by tui_monitor.py
AGENT_ORDER = ["pm", "researcher", "developer", "reviewer", "tester", "writer"]
AGENT_SHORT = {
    "pm": "PM", "researcher": "researcher", "developer": "developer",
    "reviewer": "reviewer", "tester": "tester", "writer": "writer",
}


def display_width(text: str) -> int:
    """Calculate terminal display width of string (CJK=2 cells, ASCII=1 cell)."""
    w = 0
    for ch in text:
        eaw = unicodedata.east_asian_width(ch)
        if eaw in ("W", "F"):
            w += 2
        else:
            w += 1
    return w


def wrap_text(text: str, max_width: int) -> list[str]:
    """Wrap text to max_width. Handles CJK 2-cell width."""
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
    """Truncate text to maxlen (newlines removed)."""
    text = text.replace("\n", " ").strip()
    return text[:maxlen] + "..." if len(text) > maxlen else text


def get_at_context(cmd_buf: str):
    """Current @mention input context. Returns (prefix, partial, candidates) or None."""
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
    """Extract @agent mentions from text."""
    pattern = r"@(" + "|".join(AGENT_ORDER) + r")\b"
    return re.findall(pattern, text, re.IGNORECASE)
