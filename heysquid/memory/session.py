"""
heysquid.memory.session — session memory management.

Functions:
- load_session_memory, compact_session_memory
- _summarize_trimmed_conversations
- save_session_summary
"""

import os
from datetime import date

from ..paths import (
    DATA_DIR,
    SESSION_MEMORY_FILE,
    PERMANENT_MEMORY_FILE,
    SESSION_MEMORY_MAX_CONVERSATIONS,
)


def load_session_memory():
    """Called at session start — returns the contents of session_memory.md."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return None
    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            print(f"[MEMORY] Session memory loaded ({len(content)} chars)")
            return content
        return None
    except Exception as e:
        print(f"[WARN] Error reading session_memory.md: {e}")
        return None


def _summarize_trimmed_conversations(trimmed_lines):
    """Extract key events/tone from trimmed conversation items as a one-line summary.
    Rule-based processing without AI calls (zero token cost)."""
    if not trimmed_lines:
        return None

    # Keyword-based event extraction
    events = []
    tone_signals = {"positive": 0, "negative": 0, "work": 0}

    for line in trimmed_lines:
        text = line.strip().lstrip("- ")
        # Key event keywords
        if any(k in text for k in ["success", "complete", "posted", "성공", "완료", "게시"]):
            tone_signals["positive"] += 1
        if any(k in text for k in ["fail", "mistake", "error", "bug", "aborted", "실패", "실수", "오류", "버그", "중단"]):
            tone_signals["negative"] += 1
        if any(k in text for k in ["task", "fix", "implement", "start", "progress", "작업", "수정", "구현", "시작", "진행"]):
            tone_signals["work"] += 1
        # Extract events from bot or user markers (key actions only)
        if "\U0001f916" in text:
            # Verb-based key extraction
            for keyword in ["posted", "reply", "fix", "send", "briefing", "analyze", "save", "complete",
                           "게시 성공", "답글", "수정", "전송", "브리핑", "분석", "저장", "완료"]:
                if keyword in text:
                    short = text.split("\U0001f916")[1].strip()[:40]
                    events.append(short)
                    break
        elif "\U0001f464" in text:
            for keyword in ["please", "post", "add", "show", "write", "extract", "find",
                           "해줘", "올려", "달아", "보여", "써", "뽑아", "찾아"]:
                if keyword in text:
                    short = text.split("\U0001f464")[1].strip()[:30]
                    events.append(short)
                    break

    if not events:
        return None

    # Determine tone
    dominant = max(tone_signals, key=tone_signals.get)
    tone_map = {"positive": "✅smooth", "negative": "⚠️issues", "work": "🔧work-focused"}
    tone = tone_map.get(dominant, "")

    # Up to 3 events + tone
    summary_events = events[:3]
    summary = f"  → [{tone}] " + " / ".join(summary_events)
    return summary


def compact_session_memory():
    """Trim the 'Recent Conversations' section when it exceeds 50 entries.
    Preserves context by leaving a one-line summary of trimmed conversations."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[WARN] Error reading session_memory.md: {e}")
        return

    lines = content.split("\n")

    # Find 'Recent Conversations' section
    conv_start = None
    conv_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## 최근 대화") or line.strip().startswith("## Recent"):
            conv_start = i + 1
        elif conv_start is not None and line.strip().startswith("## "):
            conv_end = i
            break

    if conv_start is None:
        return

    if conv_end is None:
        conv_end = len(lines)

    # Extract conversation entries (lines starting with - )
    conv_lines = [l for l in lines[conv_start:conv_end] if l.strip().startswith("- ")]
    other_lines = [l for l in lines[conv_start:conv_end] if not l.strip().startswith("- ") and l.strip()]

    if len(conv_lines) <= SESSION_MEMORY_MAX_CONVERSATIONS:
        return  # No cleanup needed

    # Delete oldest entries (from the front)
    trimmed = len(conv_lines) - SESSION_MEMORY_MAX_CONVERSATIONS
    trimmed_lines = conv_lines[:trimmed]
    conv_lines = conv_lines[trimmed:]
    print(f"[COMPACT] Session memory cleanup: {trimmed} old conversations removed")

    # Generate tone/event memo for trimmed conversations
    summary = _summarize_trimmed_conversations(trimmed_lines)
    if summary:
        # Add new summary on top of existing summary memos (starting with →)
        conv_lines = [summary] + conv_lines
        print(f"[COMPACT] Tone/event memo added: {summary.strip()}")

    # Reassemble
    new_section = other_lines + conv_lines
    new_lines = lines[:conv_start] + new_section + lines[conv_end:]
    new_content = "\n".join(new_lines)

    with open(SESSION_MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


def save_session_summary():
    """For session end/crash safety — records 'top 3 highlights of the day' in permanent_memory.md.
    Extracts key events from session_memory.md and records them by date.
    Overwrites if an entry for today already exists."""
    today = date.today().strftime("%m/%d")

    # Read session_memory
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            session_content = f.read()
    except Exception:
        return

    # Extract top 3 key events from recent conversations
    events = []
    for line in session_content.split("\n"):
        text = line.strip()
        if not text.startswith("- "):
            continue
        # Extract only significant events
        for keyword in ["success", "complete", "approved", "fix", "implement", "fail", "decided", "confirmed", "save", "posted",
                        "성공", "완료", "승인", "수정", "구현", "실패", "결정", "확정", "저장", "게시"]:
            if keyword in text:
                # Strip timestamp, keep the essentials
                clean = text.lstrip("- ").strip()
                # Text after bot/user marker only
                for marker in ["\U0001f916 ", "\U0001f464 "]:
                    if marker in clean:
                        clean = clean.split(marker, 1)[1]
                        break
                if len(clean) > 60:
                    clean = clean[:60] + "..."
                events.append(clean)
                break

    if not events:
        return

    # Maximum 3 lines
    summary_lines = events[-3:]  # Most recent 3

    # Read permanent_memory.md
    perm_file = PERMANENT_MEMORY_FILE
    if not os.path.exists(perm_file):
        return

    try:
        with open(perm_file, "r", encoding="utf-8") as f:
            perm_content = f.read()
    except Exception:
        return

    # Find or create 'Session Key Log' section
    section_header = "## Session Key Log"
    legacy_header = "## 세션 핵심 로그"
    summary_text = f"- [{today}] " + " | ".join(summary_lines)

    # Support both new and legacy Korean header
    if section_header in perm_content or legacy_header in perm_content:
        if legacy_header in perm_content and section_header not in perm_content:
            section_header = legacy_header
        # Append to existing section (replace if same date)
        lines = perm_content.split("\n")
        section_idx = None
        next_section_idx = None
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                section_idx = i
            elif section_idx is not None and i > section_idx and line.strip().startswith("## "):
                next_section_idx = i
                break

        if section_idx is not None:
            if next_section_idx is None:
                next_section_idx = len(lines)

            # Remove entries with the same date
            section_lines = []
            for line in lines[section_idx + 1:next_section_idx]:
                if line.strip().startswith(f"- [{today}]"):
                    continue  # Replace same date
                section_lines.append(line)

            # Add new entry (keep up to 7 days)
            entry_lines = [l for l in section_lines if l.strip().startswith("- [")]
            if len(entry_lines) >= 7:
                # Remove the oldest entry
                for j, l in enumerate(section_lines):
                    if l.strip().startswith("- ["):
                        section_lines.pop(j)
                        break

            section_lines.append(summary_text)

            new_lines = lines[:section_idx + 1] + section_lines + lines[next_section_idx:]
            perm_content = "\n".join(new_lines)
    else:
        # Add new section (at end of file)
        perm_content = perm_content.rstrip() + f"\n\n{section_header}\n{summary_text}\n"

    try:
        with open(perm_file, "w", encoding="utf-8") as f:
            f.write(perm_content)
        print(f"[SUMMARY] Today's top 3 highlights saved to permanent_memory")
    except Exception as e:
        print(f"[WARN] Failed to write permanent_memory: {e}")
