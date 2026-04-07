#!/usr/bin/env python3
"""
스레드 소재 제안 → 텔레그램 전송 → 사용자 컨펌 대기.

06:30 cron으로 실행:
  python3 scripts/threads_suggest.py

흐름:
  1. 7소스 뉴스 수집 + 트렌드 수집
  2. 스코어링 → TOP 5 선별
  3. data/threads_suggestions.json에 저장
  4. 텔레그램으로 번호 매긴 리스트 전송
  5. 사용자가 "1번 3번" 답장 → executor → SQUID가 초안 작성 → 큐 등록
"""

import json
import logging
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SUGGESTIONS_FILE = os.path.join(PROJECT_ROOT, "data", "threads_suggestions.json")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [suggest] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def collect_and_score():
    """7소스 뉴스 수집 + 스코어링 → TOP 5 thread-worthy 선별."""
    from heysquid.automations.briefing._news_fetcher import fetch_all_news_sources
    from heysquid.automations.briefing._news_scorer import (
        score_and_rank_news,
        select_thread_worthy,
    )

    logger.info("뉴스 7소스 수집 시작...")
    all_news = fetch_all_news_sources()
    logger.info(f"수집 완료: {len(all_news)}건")

    if not all_news:
        logger.warning("수집된 뉴스 없음")
        return []

    # 스코어링 (select_thread_worthy가 내부에서 스코어 사용)
    score_and_rank_news(all_news, top_n=10)

    # 스레드 맞춤 선별 TOP 5
    thread_picks = select_thread_worthy(all_news, top_n=5)
    logger.info(f"스레드 맞춤 {len(thread_picks)}건 선별")

    return thread_picks


def collect_trends():
    """트렌드 수집 (signal.bz + 이지텍스트)."""
    try:
        from scripts.trend_collector import collect_all, save_trends

        entry = collect_all()
        save_trends(entry)
        logger.info(
            f"트렌드 저장: signal={len(entry.get('signal_bz', []))} "
            f"google={len(entry.get('google_trends', []))} "
            f"threads={len(entry.get('threads_trends', []))}"
        )
        return entry
    except Exception as e:
        logger.warning(f"트렌드 수집 실패: {e}")
        return {}


def save_suggestions(picks, trends=None):
    """선별 결과를 JSON으로 저장. SQUID가 컨펌 처리할 때 읽음."""
    now = datetime.now()
    suggestions = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "status": "waiting",  # waiting → confirmed → drafted
        "picks": [],
        "trends_summary": {},
    }

    for i, pick in enumerate(picks, 1):
        item = pick["item"]
        suggestions["picks"].append({
            "num": i,
            "title": item["title"],
            "url": item["url"],
            "source": item.get("source", ""),
            "score": item.get("_score", 0),
            "pattern": pick.get("pattern", ""),
            "reason": pick.get("reason", ""),
            "points": item.get("points", 0),
            "comments": item.get("comments", 0),
            "selected": False,
        })

    # 트렌드 요약 (signal.bz TOP 5, 구글 TOP 5)
    if trends:
        suggestions["trends_summary"] = {
            "signal_top5": [
                s.get("keyword", "") for s in trends.get("signal_bz", [])[:5]
            ],
            "google_top5": [
                g.get("keyword", "") for g in trends.get("google_trends", [])[:5]
            ],
            "threads_top3": [
                t.get("keyword", "") for t in trends.get("threads_trends", [])[:3]
            ],
        }

    os.makedirs(os.path.dirname(SUGGESTIONS_FILE), exist_ok=True)
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)

    logger.info(f"저장 완료: {SUGGESTIONS_FILE}")
    return suggestions


def format_telegram_message(suggestions):
    """텔레그램으로 보낼 소재 리스트 포맷."""
    now = datetime.now()
    weekday = ["월", "화", "수", "목", "금", "토", "일"][now.weekday()]
    date_str = f"{now.month}/{now.day}({weekday})"

    lines = [f"오늘 스레드 소재 TOP 5 — {date_str}", ""]

    for pick in suggestions["picks"]:
        num = pick["num"]
        title = pick["title"]
        source = pick["source"]
        pattern = pick["pattern"]
        score = pick["score"]
        lines.append(f"{num}. {title}")
        lines.append(f"   [{source}] {pattern} ({score:.0f}점)")
        lines.append("")

    # 트렌드 한줄 요약
    ts = suggestions.get("trends_summary", {})
    signal = ts.get("signal_top5", [])
    if signal:
        lines.append(f"네이버: {', '.join(signal[:3])}")

    google = ts.get("google_top5", [])
    if google:
        lines.append(f"구글: {', '.join(google[:3])}")

    lines.append("")
    lines.append("올릴 거 번호로 답장해! (예: 1번 3번)")

    return "\n".join(lines)


def send_to_telegram(text):
    """텔레그램 전송."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_ROOT, "heysquid", ".env"))

        chat_id = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")[0].strip()
        if not chat_id:
            logger.error("TELEGRAM_ALLOWED_USERS not set")
            return False

        from heysquid.channels.telegram import send_message_sync
        success = send_message_sync(int(chat_id), text, parse_mode=None, _save=False)

        if success:
            logger.info("텔레그램 전송 완료")
        else:
            logger.error("텔레그램 전송 실패")
        return success

    except Exception as e:
        logger.error(f"텔레그램 전송 오류: {e}")
        return False


def write_drafts_with_squid(suggestions):
    """Claude CLI로 5개 소재 전부 초안 작성. context.md 기반."""
    import subprocess

    picks_info = ""
    for pick in suggestions["picks"]:
        picks_info += f"\n{pick['num']}. {pick['title']}\n   URL: {pick['url']}\n   소스: {pick['source']}\n   패턴: {pick['pattern']}\n"

    prompt = (
        "workspaces/threads/context.md를 읽어. 이게 스레드 글쓰기 공식이야. 반드시 따라야 해.\n\n"
        "다음 소재들로 ambition_monkey 계정용 스레드 초안을 써.\n"
        f"{picks_info}\n"
        "각 소재마다:\n"
        "1. URL이 있으면 기사를 읽어서 팩트를 파악해\n"
        "2. context.md의 3단 구조(훅-본문-참여유도)로 본문 작성\n"
        "3. 댓글1 (인사이트 추가) 작성\n"
        "4. CTA댓글 작성 (매번 다르게)\n"
        "5. AI/테크 계정에 안 맞는 소재는 '스킵 추천'이라고만 써\n\n"
        "규칙:\n"
        "- 훅 15자 이하\n"
        "- 해석 > 정보. '이게 나한테 뭘 의미하는지'가 핵심\n"
        "- 마무리 5개 전부 다른 패턴 (강한의견/관찰+질문/혼잣말/직접질문/역설)\n"
        "- 이모지 1-2개, 해시태그 1개\n"
        "- 개인 경험/반응 섞기\n"
        "- 템플릿화 금지. 글마다 구조가 달라야 해\n"
        "- 뉴스 기반 글은 댓글에 원문 출처 링크 필수 (본문에는 절대 안 넣음)\n"
        "- CTA '팔로우 🔥' 반복 절대 금지. 봇 티 남. 5개 중 1~2개는 CTA 없이 여운으로 끝내\n\n"
        "결과를 data/threads_drafts_today.json에 저장해.\n"
        "형식: {\"drafts\": [{\"num\": 1, \"title\": ..., \"skip\": false, "
        "\"text\": 본문, \"first_reply\": 댓글1, \"cta\": CTA댓글, "
        "\"hook_type\": 사용한 훅 유형}, ...]}\n"
        "skip이 true인 건 text를 '스킵 추천: (이유)'로."
    )

    claude_cmd = None
    for path in [
        "/mnt/c/Users/hyuk/AppData/Roaming/npm/claude",
        os.path.expanduser("~/.local/bin/claude"),
        "/usr/local/bin/claude",
    ]:
        if os.path.exists(path):
            claude_cmd = path
            break

    if not claude_cmd:
        claude_cmd = "claude"

    # 프롬프트를 파일로 저장 (쉘 인자 길이 제한 회피)
    prompt_file = os.path.join(PROJECT_ROOT, "data", "threads_suggest_prompt.txt")
    with open(prompt_file, "w", encoding="utf-8") as f:
        f.write(prompt)

    try:
        logger.info("Claude CLI로 초안 작성 시작...")
        # stdin으로 프롬프트 전달
        result = subprocess.run(
            [claude_cmd, "-p", "--dangerously-skip-permissions", "--model", "sonnet"],
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT, "CLAUDECODE": ""},
            input=prompt,
            timeout=600,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info("초안 작성 완료")
            drafts_file = os.path.join(PROJECT_ROOT, "data", "threads_drafts_today.json")
            if os.path.exists(drafts_file):
                with open(drafts_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning("drafts JSON 파일이 생성되지 않음")
                logger.info(f"Claude 출력: {result.stdout[:500]}")
        else:
            logger.warning(f"Claude CLI 실패 (rc={result.returncode}): {result.stderr[:300]}")
    except subprocess.TimeoutExpired:
        logger.warning("Claude CLI 타임아웃 (600s)")
    except Exception as e:
        logger.warning(f"Claude CLI 오류: {e}")

    return None


def send_drafts_to_telegram(drafts_data):
    """각 초안을 개별 텔레그램 메시지로 전송."""
    if not drafts_data or "drafts" not in drafts_data:
        return

    drafts = drafts_data["drafts"]
    total = len(drafts)

    for draft in drafts:
        num = draft.get("num", "?")
        title = draft.get("title", "")
        skip = draft.get("skip", False)

        if skip:
            msg = f"[{num}/{total}] {title}\n\n{draft.get('text', '스킵 추천')}"
        else:
            text = draft.get("text", "")
            first_reply = draft.get("first_reply", "")
            cta = draft.get("cta", "")
            hook_type = draft.get("hook_type", "")

            msg = f"[{num}/{total}] {hook_type}\n\n{text}"
            if first_reply:
                msg += f"\n\n---\n[댓글1]\n{first_reply}"
            if cta:
                msg += f"\n\n[CTA]\n{cta}"

        send_to_telegram(msg)
        import time
        time.sleep(2)  # rate limit — event loop 재생성 여유

    # Final pick message
    send_to_telegram("어떤 거 올릴까? 번호로 답장해! (예: 1번 3번)")


def load_suggestions():
    """저장된 소재 제안 로드."""
    if not os.path.exists(SUGGESTIONS_FILE):
        return None
    with open(SUGGESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_selection(text):
    """사용자 답장에서 선택 번호 파싱.

    "1번 3번", "1, 3", "1 3", "1번3번", "13", "1번이랑 3번" 등 지원.
    """
    import re
    numbers = re.findall(r'(\d)', text)
    return sorted(set(int(n) for n in numbers if 1 <= int(n) <= 5))


def mark_selected(nums):
    """선택된 번호를 suggestions에 표시하고 선택된 picks 반환."""
    suggestions = load_suggestions()
    if not suggestions:
        logger.error("suggestions 파일 없음")
        return []

    selected = []
    for pick in suggestions["picks"]:
        if pick["num"] in nums:
            pick["selected"] = True
            selected.append(pick)

    suggestions["status"] = "confirmed"
    suggestions["confirmed_at"] = datetime.now().isoformat()
    suggestions["confirmed_nums"] = nums

    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(suggestions, f, ensure_ascii=False, indent=2)

    logger.info(f"컨펌 완료: {nums}")
    return selected


def add_to_queue(posts_data):
    """초안을 threads_queue.json에 등록.

    Args:
        posts_data: list of dict with keys: text, first_reply, reply_chain, account, time
    """
    queue_file = os.path.join(PROJECT_ROOT, "data", "threads_queue.json")
    if os.path.exists(queue_file):
        with open(queue_file, "r", encoding="utf-8") as f:
            queue = json.load(f)
    else:
        queue = {"posts": []}

    posts = queue.get("posts", [])
    max_id = max((p.get("id", 0) for p in posts), default=0)
    today = datetime.now().strftime("%Y-%m-%d")

    added = []
    for pd in posts_data:
        max_id += 1
        new_post = {
            "id": max_id,
            "date": today,
            "time": pd.get("time", "09:00"),
            "text": pd["text"],
            "first_reply": pd.get("first_reply"),
            "reply_chain": pd.get("reply_chain", []),
            "image": None,
            "status": "pending",
            "account": pd.get("account", "ambition_monkey"),
        }
        posts.append(new_post)
        added.append(new_post)
        logger.info(f"큐 등록 #{max_id}: {today} {pd.get('time')} — {pd['text'][:50]}...")

    queue["posts"] = posts
    with open(queue_file, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)

    return added


def main():
    import argparse

    parser = argparse.ArgumentParser(description="스레드 소재 제안")
    parser.add_argument("--confirm", metavar="NUMS", help="컨펌 (예: '1,3' 또는 '1번 3번')")
    parser.add_argument("--show", action="store_true", help="현재 소재 제안 보기")
    args = parser.parse_args()

    if args.show:
        suggestions = load_suggestions()
        if not suggestions:
            print("저장된 소재 제안 없음")
            return
        print(format_telegram_message(suggestions))
        return

    if args.confirm:
        nums = parse_selection(args.confirm)
        if not nums:
            print("유효한 번호가 없어. (1~5)")
            return
        selected = mark_selected(nums)
        if selected:
            print(f"선택됨: {[s['num'] for s in selected]}")
            for s in selected:
                print(f"  {s['num']}. {s['title']} [{s['source']}]")
        return

    # 기본: 수집 → 초안 작성 → 텔레그램 전송
    logger.info("=== 스레드 소재 제안 시작 ===")

    # 1. 트렌드 수집
    trends = collect_trends()

    # 2. 뉴스 수집 + 스코어링
    picks = collect_and_score()

    if not picks:
        send_to_telegram("오늘 스레드 소재로 쓸만한 뉴스가 없네. 나중에 다시 확인해볼게!")
        return

    # 3. JSON 저장
    suggestions = save_suggestions(picks, trends)

    # 4. Claude CLI로 5개 전부 초안 작성 (context.md 기반)
    drafts_data = write_drafts_with_squid(suggestions)

    if drafts_data:
        # 5. 각 초안을 개별 텔레그램 메시지로 전송
        send_drafts_to_telegram(drafts_data)
    else:
        # fallback: 초안 작성 실패 시 제목만 전송
        message = format_telegram_message(suggestions)
        print(message)
        send_to_telegram(message)

    logger.info("=== 소재 제안 완료 ===")


if __name__ == "__main__":
    main()
