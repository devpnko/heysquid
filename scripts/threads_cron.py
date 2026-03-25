#!/usr/bin/env python3
"""
Threads 예약 게시 cron 스크립트.

사용법:
  python3 scripts/threads_cron.py              — 현재 시간에 맞는 pending 게시물 실행
  python3 scripts/threads_cron.py --list       — 오늘 예약된 게시물 목록
  python3 scripts/threads_cron.py --add "텍스트" --time 08:00  — 게시물 추가
  python3 scripts/threads_cron.py --add "텍스트" --time 08:00 --reply "첫댓글" --account user
  python3 scripts/threads_cron.py --fortune    — 오늘 운세 자동 생성 + 게시 + 텔레그램 알림
  python3 scripts/threads_cron.py --generate-week — 이번 주 운세 큐에 일괄 등록
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta

# Project paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
QUEUE_FILE = os.path.join(PROJECT_ROOT, "data", "threads_queue.json")
BROWSER_DATA = os.path.join(PROJECT_ROOT, "data", "threads_browser_data")

# Add project root to sys.path for heysquid imports
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [threads_cron] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Queue I/O ---


def load_queue() -> dict:
    """Load the queue file. Creates default if missing."""
    if not os.path.exists(QUEUE_FILE):
        return {"posts": []}
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_queue(data: dict) -> None:
    """Save queue back to disk."""
    os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- Threads posting (Playwright, from threads_upload.py pattern) ---


def _clean_locks():
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(BROWSER_DATA, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _create_context(playwright, headless=True):
    os.makedirs(BROWSER_DATA, exist_ok=True)
    _clean_locks()
    return playwright.chromium.launch_persistent_context(
        BROWSER_DATA,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )


def _is_logged_in(page) -> bool:
    post_btn = page.query_selector('div[role="button"]:has-text("Post")')
    whatsnew = page.query_selector('[placeholder*="new"]')
    return bool(post_btn or whatsnew)


def _open_compose(page) -> bool:
    whatsnew = page.query_selector('[contenteditable="true"]')
    if whatsnew:
        whatsnew.click()
        time.sleep(2)
        return True
    for selector in (
        '[aria-label="Create"]',
        '[aria-label="새로운 스레드"]',
        '[aria-label="New thread"]',
    ):
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                time.sleep(2)
                return True
        except Exception:
            continue
    return False


def _type_text(page, text: str) -> bool:
    for selector in (
        '[contenteditable="true"]',
        'div[role="textbox"]',
        'p[data-placeholder]',
    ):
        try:
            el = page.wait_for_selector(selector, timeout=5000)
            if el:
                el.click()
                time.sleep(0.5)
                page.keyboard.type(text, delay=30)
                time.sleep(1)
                return True
        except Exception:
            continue
    return False


def _click_post(page) -> bool:
    buttons = page.query_selector_all('div[role="button"]')
    found_cancel = False
    for btn in buttons:
        try:
            text = btn.inner_text().strip()
            if text in ("Cancel", "취소"):
                found_cancel = True
                continue
            if found_cancel and text in ("Post", "게시") and btn.is_visible():
                btn.click()
                time.sleep(5)
                return True
        except Exception:
            continue
    return False


def _post_first_reply(page, reply_text: str) -> bool:
    time.sleep(3)
    for selector in (
        '[contenteditable="true"]',
        'div[role="textbox"]',
        'p[data-placeholder]',
    ):
        try:
            el = page.wait_for_selector(selector, timeout=5000)
            if el:
                el.click()
                time.sleep(0.5)
                page.keyboard.type(reply_text, delay=30)
                time.sleep(1)
                reply_btns = page.query_selector_all('div[role="button"]')
                for btn in reply_btns:
                    try:
                        txt = btn.inner_text().strip()
                        if txt in ("Reply", "답글", "Post", "게시") and btn.is_visible():
                            btn.click()
                            time.sleep(3)
                            return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def post_to_threads(text: str, first_reply: str = None, image: str = None) -> dict:
    """Post to Threads using Playwright persistent context."""
    if not os.path.exists(BROWSER_DATA):
        return {"ok": False, "error": "No browser session. Run: python3 scripts/threads_upload.py --login"}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            context = _create_context(p, headless=True)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                page.goto("https://www.threads.net/", timeout=30000)
                time.sleep(5)

                if not _is_logged_in(page):
                    return {"ok": False, "error": "Not logged in"}

                if not _open_compose(page):
                    return {"ok": False, "error": "Failed to open compose"}

                if not _type_text(page, text):
                    return {"ok": False, "error": "Failed to type text"}

                # Image attachment
                if image and os.path.exists(image):
                    try:
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(os.path.abspath(image))
                            time.sleep(3)
                    except Exception:
                        logger.warning("Image attach failed, posting text only")

                if not _click_post(page):
                    return {"ok": False, "error": "Failed to click Post"}

                if first_reply:
                    if _post_first_reply(page, first_reply):
                        logger.info("First reply posted")
                    else:
                        logger.warning("First reply failed")

                return {"ok": True}

            finally:
                context.close()

    except Exception as e:
        return {"ok": False, "error": str(e)}


# --- Telegram notification ---


def _notify_telegram(text: str):
    """Send a notification to Telegram. Silently fails if telegram is unavailable."""
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(PROJECT_ROOT, "heysquid", ".env"))

        chat_id = os.getenv("TELEGRAM_ALLOWED_USERS")
        if not chat_id:
            logger.warning("TELEGRAM_ALLOWED_USERS not set, skipping notification")
            return

        from heysquid.channels.telegram import send_message_sync
        send_message_sync(chat_id, text, parse_mode=None, _save=False)
        logger.info("Telegram notification sent")
    except Exception as e:
        logger.warning(f"Telegram notification failed: {e}")


# --- Commands ---


def cmd_fortune():
    """Generate today's fortune and post to Threads immediately."""
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    logger.info(f"Generating fortune for {today_str}...")

    try:
        from heysquid.skills.threads_fortune._generator import generate_daily_fortune
    except ImportError as e:
        err = f"Fortune generator import failed: {e}"
        logger.error(err)
        _notify_telegram(f"❌ 스레드 운세 게시 실패\n{err}")
        return

    fortune_text = generate_daily_fortune(today)
    first_reply = "👇가장 정확한 오늘의 운세는 여기 DKBSQD.com 🔮"

    logger.info(f"Fortune generated ({len(fortune_text)} chars), posting...")

    result = post_to_threads(fortune_text, first_reply=first_reply)

    if result.get("ok"):
        logger.info("Fortune posted successfully")
        _notify_telegram(
            f"✅ 스레드 운세 게시 완료\n"
            f"{today.month}/{today.day} 띠별 운세"
        )
        # collect 실행
        try:
            import subprocess
            subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "threads_engage.py"), "collect", "--count", "10"],
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
                timeout=120,
            )
            logger.info("Engage collect completed")
        except Exception as e:
            logger.warning(f"Engage collect failed: {e}")
    else:
        error = result.get("error", "unknown")
        logger.error(f"Fortune post failed: {error}")
        _notify_telegram(f"❌ 스레드 운세 게시 실패\n{error}")


def cmd_generate_week():
    """Generate fortunes for the rest of this week and enqueue at 08:00 each day."""
    today = date.today()
    # Find remaining days: today through Sunday
    days_until_sunday = 6 - today.weekday()  # weekday: 0=Mon, 6=Sun
    if days_until_sunday < 0:
        days_until_sunday = 0  # today is Sunday, just do today

    dates = [today + timedelta(days=i) for i in range(days_until_sunday + 1)]

    try:
        from heysquid.skills.threads_fortune._generator import generate_daily_fortune
    except ImportError as e:
        logger.error(f"Fortune generator import failed: {e}")
        return

    queue = load_queue()
    posts = queue.get("posts", [])
    max_id = max((p.get("id", 0) for p in posts), default=0)

    added = 0
    for d in dates:
        date_str = d.strftime("%Y-%m-%d")

        # Skip if already queued for this date
        already = any(
            p.get("date") == date_str and "운세" in p.get("text", "")[:20]
            for p in posts
        )
        if already:
            logger.info(f"Skipping {date_str} — already queued")
            continue

        fortune_text = generate_daily_fortune(d)
        first_reply = "👇가장 정확한 오늘의 운세는 여기 DKBSQD.com 🔮"

        max_id += 1
        new_post = {
            "id": max_id,
            "date": date_str,
            "time": "08:00",
            "text": fortune_text,
            "first_reply": first_reply,
            "image": None,
            "status": "pending",
            "account": "default",
        }
        posts.append(new_post)
        added += 1
        logger.info(f"Queued #{max_id}: {date_str} 08:00 — {fortune_text[:50]}...")

    queue["posts"] = posts
    save_queue(queue)
    print(f"Added {added} fortune posts ({dates[0]} ~ {dates[-1]})")


def cmd_run():
    """Execute pending posts scheduled for the current time."""
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    current_time = now.strftime("%H:%M")

    queue = load_queue()
    posts = queue.get("posts", [])

    targets = [
        p for p in posts
        if p.get("status") == "pending"
        and p.get("date") == today
        and p.get("time") == current_time
    ]

    if not targets:
        logger.info(f"No pending posts for {today} {current_time}")
        return

    posted_any = False
    for post in targets:
        post_id = post.get("id", "?")
        text = post.get("text", "")
        first_reply = post.get("first_reply")
        image = post.get("image")

        logger.info(f"Posting #{post_id}: {text[:50]}...")

        result = post_to_threads(text, first_reply=first_reply, image=image)

        if result.get("ok"):
            post["status"] = "posted"
            post["posted_at"] = now.isoformat()
            logger.info(f"#{post_id} posted successfully")
            posted_any = True
            _notify_telegram(f"✅ 스레드 게시 완료 #{post_id}\n{text[:80]}...")
        else:
            post["status"] = "failed"
            post["error"] = result.get("error", "unknown")
            logger.error(f"#{post_id} failed: {result.get('error')}")
            _notify_telegram(f"❌ 스레드 게시 실패 #{post_id}\n{result.get('error', 'unknown')}")

    save_queue(queue)

    # 게시 성공 → collect 실행 (SQUID가 다음 세션에서 댓글 작성+post)
    if posted_any:
        try:
            import subprocess
            subprocess.run(
                [sys.executable, os.path.join(SCRIPT_DIR, "threads_engage.py"), "collect", "--count", "10"],
                cwd=PROJECT_ROOT,
                env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
                timeout=120,
            )
            logger.info("Engage collect completed — SQUID will write comments next session")
        except Exception as e:
            logger.warning(f"Engage collect failed: {e}")


def cmd_list():
    """List today's scheduled posts."""
    today = datetime.now().strftime("%Y-%m-%d")
    queue = load_queue()
    posts = queue.get("posts", [])

    todays = [p for p in posts if p.get("date") == today]

    if not todays:
        print(f"No posts scheduled for {today}")
        return

    print(f"=== {today} scheduled posts ({len(todays)}) ===")
    for p in sorted(todays, key=lambda x: x.get("time", "")):
        status = p.get("status", "?")
        icon = {"pending": "⏳", "posted": "✅", "failed": "❌"}.get(status, "?")
        text_preview = p.get("text", "")[:60]
        reply_mark = " [+reply]" if p.get("first_reply") else ""
        print(f"  {icon} {p.get('time', '??:??')} | #{p.get('id', '?')} | {status} | {text_preview}{reply_mark}")


def cmd_add(text: str, time_str: str, first_reply: str = None, account: str = None):
    """Add a new post to the queue."""
    queue = load_queue()
    posts = queue.get("posts", [])

    # Next ID
    max_id = max((p.get("id", 0) for p in posts), default=0)
    new_id = max_id + 1

    today = datetime.now().strftime("%Y-%m-%d")
    new_post = {
        "id": new_id,
        "date": today,
        "time": time_str,
        "text": text,
        "first_reply": first_reply,
        "image": None,
        "status": "pending",
        "account": account or "default",
    }

    posts.append(new_post)
    queue["posts"] = posts
    save_queue(queue)

    print(f"Added #{new_id}: {today} {time_str} — {text[:50]}...")


def cmd_report():
    """오늘 예약된 게시물 전체를 텔레그램으로 보고."""
    today_str = datetime.now().strftime("%Y-%m-%d")
    today = datetime.now()
    weekday = ["월", "화", "수", "목", "금", "토", "일"][today.weekday()]

    queue = load_queue()
    posts = queue.get("posts", [])
    todays = sorted(
        [p for p in posts if p.get("date") == today_str],
        key=lambda x: x.get("time", ""),
    )

    if not todays:
        _notify_telegram(f"📋 {today.month}/{today.day}({weekday}) 스레드 예약: 없음")
        return

    lines = [f"📋 {today.month}/{today.day}({weekday}) 스레드 예약 ({len(todays)}개)\n"]
    for p in todays:
        status = p.get("status", "?")
        icon = {"pending": "⏳", "posted": "✅", "failed": "❌"}.get(status, "?")
        time_str = p.get("time", "??:??")
        text_preview = p.get("text", "")[:60].replace("\n", " ")
        lines.append(f"{icon} {time_str} #{p.get('id','?')} {text_preview}...")

    _notify_telegram("\n".join(lines))
    logger.info(f"Daily report sent: {len(todays)} posts")


def main():
    parser = argparse.ArgumentParser(description="Threads 예약 게시 cron")
    parser.add_argument("--list", action="store_true", help="오늘 예약 목록")
    parser.add_argument("--add", metavar="TEXT", help="게시물 추가")
    parser.add_argument("--time", metavar="HH:MM", help="예약 시간 (--add와 함께)")
    parser.add_argument("--reply", metavar="TEXT", help="첫댓글 (--add와 함께)")
    parser.add_argument("--account", metavar="NAME", help="계정 (--add와 함께)")
    parser.add_argument("--fortune", action="store_true", help="오늘 운세 자동 생성 + 게시")
    parser.add_argument("--generate-week", action="store_true", help="이번 주 운세 큐에 일괄 등록")
    parser.add_argument("--report", action="store_true", help="오늘 예약 보고서 (텔레그램)")

    args = parser.parse_args()

    if args.fortune:
        cmd_fortune()
    elif args.generate_week:
        cmd_generate_week()
    elif args.report:
        cmd_report()
    elif args.list:
        cmd_list()
    elif args.add:
        if not args.time:
            parser.error("--add requires --time HH:MM")
        cmd_add(args.add, args.time, first_reply=args.reply, account=args.account)
    else:
        cmd_run()


if __name__ == "__main__":
    main()
