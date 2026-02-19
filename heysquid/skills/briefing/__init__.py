"""
일일 브리핑 생성기 — heysquid

매일 아침 프로젝트 상태를 분석하여 텔레그램으로 전송.

분석 대상:
- 각 워크스페이스의 git log (최근 24h)
- tasks/ 디렉토리 (미처리 작업)
- workspaces/{name}/progress.md
- 멀티소스 IT/AI 뉴스 TOP 5
- 스레드 글 초안 자동 생성

사용법:
    python briefing.py          # 수동 실행
    (launchd로 매일 09:00 자동 실행)
"""

import os
import json
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv

# 경로 설정
from ...core.config import PROJECT_ROOT_STR as PROJECT_ROOT, WORKSPACES_DIR, get_env_path
from ...core.paths import MESSAGES_FILE

# 서브모듈
from ._news_fetcher import (
    fetch_geeknews_top,
    fetch_all_news_sources,
    AI_KEYWORDS,
    _scrape_summary,
)
from ._news_scorer import (
    score_and_rank_news,
    pick_best_per_criterion,
    select_thread_worthy,
)
from ._thread_drafter import (
    generate_thread_drafts,
    format_thread_drafts,
    save_thread_drafts,
)

# .env 로드
load_dotenv(get_env_path())

CHAT_ID = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()


def get_git_summary(repo_path):
    """
    Git 저장소의 최근 24시간 커밋 요약

    Args:
        repo_path: Git 저장소 경로

    Returns:
        str: 커밋 요약 텍스트
    """
    if not os.path.exists(os.path.join(repo_path, ".git")):
        return "(git 저장소 아님)"

    try:
        since = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        result = subprocess.run(
            ["git", "log", "--oneline", f"--since={since}", "--no-merges"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return "(git log 오류)"

        lines = result.stdout.strip().split("\n")
        lines = [l for l in lines if l.strip()]

        if not lines:
            return "최근 24시간 커밋 없음"

        return f"최근 24시간 커밋 {len(lines)}건:\n" + "\n".join(f"  - {l}" for l in lines[:10])

    except subprocess.TimeoutExpired:
        return "(git log 타임아웃)"
    except Exception as e:
        return f"(git 오류: {e})"


def get_pending_tasks():
    """미처리 텔레그램 메시지 수 확인"""
    messages_file = MESSAGES_FILE

    if not os.path.exists(messages_file):
        return 0

    try:
        with open(messages_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        messages = data.get("messages", [])
        pending = [m for m in messages if not m.get("processed", False) and m.get("type") == "user"]
        return len(pending)

    except Exception:
        return 0


def get_recent_progress(name):
    """최근 진행 기록 (마지막 3개 항목)"""
    progress_file = os.path.join(str(WORKSPACES_DIR), name, "progress.md")

    if not os.path.exists(progress_file):
        return "진행 기록 없음"

    try:
        with open(progress_file, "r", encoding="utf-8") as f:
            content = f.read()

        # ### 으로 시작하는 항목 추출
        entries = content.split("### ")
        entries = [e.strip() for e in entries if e.strip() and not e.startswith("#")]

        if not entries:
            return "진행 기록 없음"

        # 마지막 3개
        recent = entries[-3:]
        return "\n".join(f"  - {e.split(chr(10))[0]}" for e in recent)

    except Exception:
        return "진행 기록 없음"


def format_geeknews(news_items):
    """GeekNews 뉴스를 텔레그램 포맷으로 변환"""
    if not news_items:
        return "GeekNews 뉴스를 가져오지 못했어요."

    lines = [f"GeekNews 오늘의 핫 뉴스 TOP {len(news_items)}", ""]
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"⭐ {item['url']}")
        lines.append("")

    return "\n".join(lines).strip()


def format_top_news(top_items, label="방법1: 가중치 통합 랭킹", with_scrape=True):
    """종합 뉴스를 텔레그램 포맷으로 변환. 기사 요약 포함."""
    if not top_items:
        return f"{label}을 생성하지 못했어요."

    lines = [f"\U0001f4cc {label}", ""]
    for i, item in enumerate(top_items, 1):
        src = item.get("source", "")
        score = item.get("_score", 0)
        badge = ""
        if AI_KEYWORDS.search(item["title"]):
            badge = " [AI]"
        lines.append(f"{i}. {item['title']}{badge} ({score}점)")
        lines.append(f"   [{src}] {item['url']}")
        if with_scrape:
            summary = _scrape_summary(item["url"])
            if summary:
                lines.append(f"   → {summary}")
        lines.append("")

    return "\n".join(lines).strip()


def format_criterion_picks(picks, with_scrape=True):
    """기준별 1픽을 텔레그램 포맷으로 변환. 기사 요약 포함."""
    if not picks:
        return "기준별 1픽을 생성하지 못했어요."

    lines = ["\U0001f4cc 방법2: 기준별 1픽 (5개 세트)", ""]
    for p in picks:
        item = p["item"]
        lines.append(f"{p['criterion']} → {item['title']}")
        lines.append(f"   [{item.get('source', '')}] {item['url']}")
        if with_scrape:
            summary = _scrape_summary(item["url"])
            if summary:
                lines.append(f"   → {summary}")
        lines.append("")

    return "\n".join(lines).strip()


def format_thread_picks(thread_picks):
    """스레드 맞춤 기사를 텔레그램 포맷으로 변환"""
    if not thread_picks:
        return "스레드 맞춤 기사를 선별하지 못했어요."

    lines = ["\U0001f3af 스레드 맞춤 기사 (패턴 분석 기반)", ""]
    for i, p in enumerate(thread_picks, 1):
        item = p["item"]
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   → {p['pattern']}. {p['reason']}")
        lines.append(f"   {item['url']}")
        lines.append("")

    return "\n".join(lines).strip()


def generate_briefing():
    """일일 브리핑 생성"""
    now = datetime.now()
    briefing_parts = []

    briefing_parts.append(f"**heysquid 일일 브리핑**")
    briefing_parts.append(f"{now.strftime('%Y-%m-%d %A')}")
    briefing_parts.append("")

    # 미처리 메시지
    pending = get_pending_tasks()
    if pending > 0:
        briefing_parts.append(f"**미처리 메시지: {pending}개**")
    else:
        briefing_parts.append("미처리 메시지: 없음")
    briefing_parts.append("")

    # 워크스페이스별 상태
    workspaces_file = os.path.join(PROJECT_ROOT, "data", "workspaces.json")

    if os.path.exists(workspaces_file):
        try:
            with open(workspaces_file, "r", encoding="utf-8") as f:
                workspaces = json.load(f)
        except Exception:
            workspaces = {}
    else:
        workspaces = {}

    if workspaces:
        briefing_parts.append("**프로젝트 현황:**")
        briefing_parts.append("")

        for name, info in workspaces.items():
            ws_path = info.get("path", "")
            description = info.get("description", "")
            last_active = info.get("last_active", "N/A")

            briefing_parts.append(f"--- {name} ---")
            briefing_parts.append(f"  {description}")
            briefing_parts.append(f"  최근 활동: {last_active}")

            # Git 요약
            if os.path.exists(ws_path):
                git_summary = get_git_summary(ws_path)
                briefing_parts.append(f"  {git_summary}")

            # 진행 기록
            progress = get_recent_progress(name)
            if progress != "진행 기록 없음":
                briefing_parts.append(f"  최근 진행:")
                briefing_parts.append(f"  {progress}")

            briefing_parts.append("")

    else:
        briefing_parts.append("등록된 프로젝트 없음")
        briefing_parts.append("")

    # 멀티소스 뉴스 수집 + 분석
    try:
        all_news = fetch_all_news_sources()

        # 방법1: 가중치 통합 랭킹 TOP 10
        top10 = score_and_rank_news(all_news, top_n=10)
        if top10:
            briefing_parts.append(format_top_news(top10, "방법1: 가중치 통합 랭킹 TOP 10"))
            briefing_parts.append("")

        # 방법2: 기준별 1픽 (5개 세트)
        criterion_picks = pick_best_per_criterion(all_news)
        if criterion_picks:
            briefing_parts.append(format_criterion_picks(criterion_picks))
            briefing_parts.append("")

        # 스레드 맞춤 기사 선별 (인기글 패턴 기반)
        thread_picks = select_thread_worthy(all_news, top_n=5)
        if thread_picks:
            briefing_parts.append(format_thread_picks(thread_picks))
            briefing_parts.append("")

            # 스레드 글 초안 (자연스러운 톤)
            drafts = generate_thread_drafts(thread_picks)
            if drafts:
                briefing_parts.append(format_thread_drafts(drafts))
                briefing_parts.append("")
                save_thread_drafts(drafts)

    except Exception as e:
        print(f"[WARN] 종합 뉴스/스레드 생성 오류: {e}")
        import traceback
        traceback.print_exc()
        briefing_parts.append("(종합 뉴스 수집 중 오류 발생)")
        briefing_parts.append("")

    # GeekNews TOP 10 (별도 섹션)
    news_items = fetch_geeknews_top(10)
    if news_items:
        briefing_parts.append(format_geeknews(news_items))
        briefing_parts.append("")

    briefing_parts.append("---")
    briefing_parts.append("_heysquid 자동 브리핑_")

    return "\n".join(briefing_parts)


def send_briefing():
    """브리핑 생성 후 텔레그램으로 전송"""
    if not CHAT_ID:
        print("[ERROR] TELEGRAM_ALLOWED_USERS가 설정되지 않았습니다.")
        return False

    briefing = generate_briefing()
    print(briefing)
    print()

    try:
        from ...channels.telegram import send_message_sync
        success = send_message_sync(int(CHAT_ID), briefing)

        if success:
            print("[OK] 브리핑 전송 완료!")
        else:
            print("[ERROR] 브리핑 전송 실패!")

        return success

    except Exception as e:
        print(f"[ERROR] 브리핑 전송 오류: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("heysquid 일일 브리핑")
    print("=" * 60)
    print()

    send_briefing()
