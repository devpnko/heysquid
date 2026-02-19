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
    """세션 시작 시 — session_memory.md 내용 반환."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return None
    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if content:
            print(f"[MEMORY] 세션 메모리 로드 완료 ({len(content)} chars)")
            return content
        return None
    except Exception as e:
        print(f"[WARN] session_memory.md 읽기 오류: {e}")
        return None


def _summarize_trimmed_conversations(trimmed_lines):
    """삭제되는 대화 항목들에서 핵심 이벤트/톤을 한 줄 요약으로 추출한다.
    AI 호출 없이 규칙 기반으로 처리 (토큰 비용 0)."""
    if not trimmed_lines:
        return None

    # 키워드 기반 이벤트 추출
    events = []
    tone_signals = {"긍정": 0, "부정": 0, "작업": 0}

    for line in trimmed_lines:
        text = line.strip().lstrip("- ")
        # 주요 이벤트 키워드
        if any(k in text for k in ["성공", "완료", "게시"]):
            tone_signals["긍정"] += 1
        if any(k in text for k in ["실패", "실수", "오류", "버그", "중단"]):
            tone_signals["부정"] += 1
        if any(k in text for k in ["작업", "수정", "구현", "시작", "진행"]):
            tone_signals["작업"] += 1
        # 🤖 또는 👤 이벤트 추출 (핵심 동작만)
        if "\U0001f916" in text:
            # 동사 기반 핵심 추출
            for keyword in ["게시 성공", "답글", "수정", "전송", "브리핑", "분석", "저장", "완료"]:
                if keyword in text:
                    short = text.split("\U0001f916")[1].strip()[:40]
                    events.append(short)
                    break
        elif "\U0001f464" in text:
            for keyword in ["해줘", "올려", "달아", "보여", "써", "뽑아", "찾아"]:
                if keyword in text:
                    short = text.split("\U0001f464")[1].strip()[:30]
                    events.append(short)
                    break

    if not events:
        return None

    # 톤 결정
    dominant = max(tone_signals, key=tone_signals.get)
    tone_map = {"긍정": "✅순조", "부정": "⚠️이슈있음", "작업": "🔧작업중심"}
    tone = tone_map.get(dominant, "")

    # 최대 3개 이벤트 + 톤
    summary_events = events[:3]
    summary = f"  → [{tone}] " + " / ".join(summary_events)
    return summary


def compact_session_memory():
    """session_memory.md의 '최근 대화' 섹션이 50개를 초과하면 오래된 것부터 삭제.
    삭제되는 대화의 핵심을 한 줄 요약으로 남겨 맥락 유지."""
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"[WARN] session_memory.md 읽기 오류: {e}")
        return

    lines = content.split("\n")

    # '최근 대화' 섹션 찾기
    conv_start = None
    conv_end = None
    for i, line in enumerate(lines):
        if line.strip().startswith("## 최근 대화"):
            conv_start = i + 1
        elif conv_start is not None and line.strip().startswith("## "):
            conv_end = i
            break

    if conv_start is None:
        return

    if conv_end is None:
        conv_end = len(lines)

    # 대화 항목 추출 (- 로 시작하는 줄)
    conv_lines = [l for l in lines[conv_start:conv_end] if l.strip().startswith("- ")]
    other_lines = [l for l in lines[conv_start:conv_end] if not l.strip().startswith("- ") and l.strip()]

    if len(conv_lines) <= SESSION_MEMORY_MAX_CONVERSATIONS:
        return  # 정리 불필요

    # 오래된 것 삭제 (앞에서부터)
    trimmed = len(conv_lines) - SESSION_MEMORY_MAX_CONVERSATIONS
    trimmed_lines = conv_lines[:trimmed]
    conv_lines = conv_lines[trimmed:]
    print(f"[COMPACT] 세션 메모리 정리: {trimmed}개 오래된 대화 삭제")

    # 삭제되는 대화의 톤/감정 메모 생성
    summary = _summarize_trimmed_conversations(trimmed_lines)
    if summary:
        # 기존 요약 메모(→로 시작) 위에 새 요약 추가
        conv_lines = [summary] + conv_lines
        print(f"[COMPACT] 톤/이벤트 메모 추가: {summary.strip()}")

    # 재조립
    new_section = other_lines + conv_lines
    new_lines = lines[:conv_start] + new_section + lines[conv_end:]
    new_content = "\n".join(new_lines)

    with open(SESSION_MEMORY_FILE, "w", encoding="utf-8") as f:
        f.write(new_content)


def save_session_summary():
    """세션 종료/크래시 대비 — permanent_memory.md에 '오늘의 핵심 3줄' 기록.
    session_memory.md에서 핵심 이벤트를 추출하여 날짜별로 기록한다.
    이미 오늘 날짜 기록이 있으면 덮어쓴다."""
    today = date.today().strftime("%m/%d")

    # session_memory 읽기
    if not os.path.exists(SESSION_MEMORY_FILE):
        return

    try:
        with open(SESSION_MEMORY_FILE, "r", encoding="utf-8") as f:
            session_content = f.read()
    except Exception:
        return

    # 최근 대화에서 핵심 이벤트 3개 추출
    events = []
    for line in session_content.split("\n"):
        text = line.strip()
        if not text.startswith("- "):
            continue
        # 중요한 이벤트만 추출
        for keyword in ["성공", "완료", "승인", "수정", "구현", "실패", "결정", "확정", "저장", "게시"]:
            if keyword in text:
                # 타임스탬프 제거하고 핵심만
                clean = text.lstrip("- ").strip()
                # 🤖/👤 이후 텍스트만
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

    # 최대 3줄
    summary_lines = events[-3:]  # 가장 최근 3개

    # permanent_memory.md 읽기
    perm_file = PERMANENT_MEMORY_FILE
    if not os.path.exists(perm_file):
        return

    try:
        with open(perm_file, "r", encoding="utf-8") as f:
            perm_content = f.read()
    except Exception:
        return

    # '세션 핵심 로그' 섹션 찾기/만들기
    section_header = "## 세션 핵심 로그"
    summary_text = f"- [{today}] " + " | ".join(summary_lines)

    if section_header in perm_content:
        # 기존 섹션에 추가 (같은 날짜면 교체)
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

            # 같은 날짜 엔트리 제거
            section_lines = []
            for line in lines[section_idx + 1:next_section_idx]:
                if line.strip().startswith(f"- [{today}]"):
                    continue  # 같은 날짜 교체
                section_lines.append(line)

            # 새 엔트리 추가 (최대 7일치 유지)
            entry_lines = [l for l in section_lines if l.strip().startswith("- [")]
            if len(entry_lines) >= 7:
                # 가장 오래된 것 제거
                for j, l in enumerate(section_lines):
                    if l.strip().startswith("- ["):
                        section_lines.pop(j)
                        break

            section_lines.append(summary_text)

            new_lines = lines[:section_idx + 1] + section_lines + lines[next_section_idx:]
            perm_content = "\n".join(new_lines)
    else:
        # 새 섹션 추가 (파일 끝)
        perm_content = perm_content.rstrip() + f"\n\n{section_header}\n{summary_text}\n"

    try:
        with open(perm_file, "w", encoding="utf-8") as f:
            f.write(perm_content)
        print(f"[SUMMARY] permanent_memory에 오늘의 핵심 3줄 기록 완료")
    except Exception as e:
        print(f"[WARN] permanent_memory 기록 실패: {e}")
