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
BROWSER_DATA_MAP = {
    "dkbsqd.official": os.path.join(PROJECT_ROOT, "data", "threads_browser_data"),
    "ambition_monkey": os.path.join(PROJECT_ROOT, "data", "threads_browser_data_ambition"),
    "default": os.path.join(PROJECT_ROOT, "data", "threads_browser_data"),
}
BROWSER_DATA = BROWSER_DATA_MAP["default"]  # 기본값


def _get_browser_data(account: str = "default") -> str:
    return BROWSER_DATA_MAP.get(account, BROWSER_DATA_MAP["default"])

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


def _clean_locks(browser_data: str = None):
    bd = browser_data or BROWSER_DATA
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(bd, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _create_context(playwright, headless=True, browser_data: str = None):
    bd = browser_data or BROWSER_DATA
    os.makedirs(bd, exist_ok=True)
    _clean_locks(bd)
    return playwright.chromium.launch_persistent_context(
        bd,
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--disable-software-rasterizer",
        ],
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


def _post_first_reply(page, reply_text: str, account: str = "dkbsqd.official", post_url: str = None) -> bool:
    """Post first reply. If post_url is given, navigate directly to that post; otherwise fall back to profile."""
    try:
        if post_url:
            page.goto(post_url, timeout=30000)
        else:
            page.goto(f"https://www.threads.net/@{account}", timeout=30000)
        time.sleep(4)

        # Click reply SVG on the first (latest) post
        replied = False
        for sel in ('svg[aria-label="Reply"]', 'svg[aria-label="답글"]'):
            btns = page.query_selector_all(sel)
            if btns:
                btns[0].click()
                time.sleep(2)
                replied = True
                break

        if not replied:
            return False

        editor = page.wait_for_selector('[contenteditable="true"]', timeout=5000)
        if not editor:
            page.keyboard.press("Escape")
            return False

        editor.click()
        time.sleep(0.3)
        page.keyboard.type(reply_text, delay=30)
        time.sleep(1)

        # Reversed search for Post button (same approach as threads_engage.py)
        post_btns = page.query_selector_all('div[role="button"]')
        target = None
        for btn in reversed(post_btns):
            try:
                txt = btn.inner_text().strip()
                if txt in ("Post", "게시") and btn.is_visible():
                    target = btn
                    break
            except Exception:
                continue

        if target:
            target.click()
            time.sleep(3)
            # 내 댓글에 좋아요 누르기
            try:
                like_btns = page.query_selector_all('svg[aria-label="Like"], svg[aria-label="좋아요"]')
                if like_btns:
                    like_btns[-1].click()
                    time.sleep(1)
                    logger.info("Liked own reply")
            except Exception:
                pass
            return True

        page.keyboard.press("Escape")
        return False

    except Exception:
        return False


def post_to_threads(text: str, first_reply: str = None, image: str = None, reply_chain: list = None, account: str = "dkbsqd.official", topic: str = None) -> dict:
    """Post to Threads using Playwright persistent context."""
    bd = _get_browser_data(account)
    if not os.path.exists(bd):
        return {"ok": False, "error": f"No browser session for {account}. Login first."}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"ok": False, "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            context = _create_context(p, headless=True, browser_data=bd)
            page = context.pages[0] if context.pages else context.new_page()

            try:
                # 게시 전 프로필의 기존 post URL 목록 저장
                existing_post_urls = set()
                try:
                    page.goto(f"https://www.threads.net/@{account}", timeout=30000)
                    time.sleep(4)
                    for link in page.query_selector_all('a[href*="/post/"]'):
                        href = link.get_attribute("href")
                        if href:
                            existing_post_urls.add(href)
                except Exception:
                    pass

                page.goto("https://www.threads.net/", timeout=30000)
                time.sleep(5)

                if not _is_logged_in(page):
                    return {"ok": False, "error": "Not logged in"}

                if not _open_compose(page):
                    return {"ok": False, "error": "Failed to open compose"}

                # 본문의 첫 번째 #해시태그 → topic으로 자동 추출 (타이핑 전에 처리)
                import re
                if not topic:
                    hashtags = re.findall(r'#(\S+)', text)
                    if hashtags:
                        topic = hashtags[0]
                # 해시태그는 topic으로 들어가니까 본문에서 제거
                if topic:
                    text = re.sub(r'\s*#\S+', '', text).rstrip()

                if not _type_text(page, text):
                    return {"ok": False, "error": "Failed to type text"}

                if topic:
                    try:
                        # "Add a topic" span을 force click → input 나타남
                        topic_span = page.query_selector('span:has-text("Add a topic")')
                        if not topic_span:
                            topic_span = page.query_selector('span:has-text("주제 추가")')

                        if topic_span:
                            topic_span.click(force=True)
                            time.sleep(1)
                            # input[placeholder="Add a topic"] 에 타이핑
                            topic_input = page.wait_for_selector(
                                'input[placeholder="Add a topic"], input[placeholder="주제 추가"]',
                                timeout=3000,
                            )
                            if topic_input:
                                topic_input.click()
                                page.keyboard.type(topic, delay=30)
                                time.sleep(2)
                                # 첫 번째 추천 선택 또는 Enter
                                page.keyboard.press("Enter")
                                time.sleep(1)
                                logger.info(f"Topic added: {topic}")
                        else:
                            logger.warning("Topic button not found, posting without topic")
                    except Exception as e:
                        logger.warning(f"Topic add failed: {e}")

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

                # 내 본문에 좋아요 + post_url 추출 — 프로필로 이동
                post_url = None
                try:
                    page.goto(f"https://www.threads.net/@{account}", timeout=30000)
                    time.sleep(4)
                    like_btns = page.query_selector_all('svg[aria-label="Like"], svg[aria-label="좋아요"]')
                    if like_btns:
                        like_btns[0].click()  # 최신 글 = 첫 번째
                        time.sleep(1)
                        logger.info("Liked own post")
                    # post_url: 기존 목록에 없는 새 URL 찾기
                    post_links = page.query_selector_all('a[href*="/post/"]')
                    for link in post_links:
                        href = link.get_attribute("href")
                        if href and href not in existing_post_urls:
                            post_url = f"https://www.threads.net{href}" if href.startswith("/") else href
                            logger.info(f"post_url (new): {post_url}")
                            break
                    if not post_url and post_links:
                        # fallback: 새 URL을 못 찾으면 첫 번째 사용
                        href = post_links[0].get_attribute("href")
                        if href:
                            post_url = f"https://www.threads.net{href}" if href.startswith("/") else href
                            logger.info(f"post_url (fallback): {post_url}")
                except Exception:
                    pass

                if first_reply:
                    if _post_first_reply(page, first_reply, account=account, post_url=post_url):
                        logger.info("First reply posted")
                    else:
                        logger.warning("First reply failed")

                # reply_chain: 추가 댓글들 순서대로 달기
                if reply_chain:
                    for idx, reply_text in enumerate(reply_chain):
                        time.sleep(2)
                        if _post_first_reply(page, reply_text, account=account, post_url=post_url):
                            logger.info(f"Reply chain [{idx+1}/{len(reply_chain)}] posted")
                        else:
                            logger.warning(f"Reply chain [{idx+1}/{len(reply_chain)}] failed")

                result = {"ok": True}
                if post_url:
                    result["post_url"] = post_url
                return result

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
        # collect + SQUID 자동 댓글 (Claude CLI)
        _run_squid_engage()
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

    current_hour = now.strftime("%H")
    targets = [
        p for p in posts
        if p.get("status") == "pending"
        and p.get("date") == today
        and p.get("time", "")[:2] == current_hour
    ]

    if not targets:
        logger.info(f"No pending posts for {today} {current_time}")
        return

    posted_accounts = set()
    for post in targets:
        post_id = post.get("id", "?")
        text = post.get("text", "")
        first_reply = post.get("first_reply")
        image = post.get("image")
        reply_chain = post.get("reply_chain")
        account = post.get("account", "dkbsqd.official")

        topic = post.get("topic")
        logger.info(f"Posting #{post_id} (@{account}): {text[:50]}...")

        result = post_to_threads(text, first_reply=first_reply, image=image, reply_chain=reply_chain, account=account, topic=topic)

        if result.get("ok"):
            post["status"] = "posted"
            post["posted_at"] = now.isoformat()
            if result.get("post_url"):
                post["post_url"] = result["post_url"]
            logger.info(f"#{post_id} posted successfully")
            posted_accounts.add(account)
            _notify_telegram(f"✅ 스레드 게시 완료 #{post_id}\n{text[:80]}...")

            # 크로스포스트 실행 (crosspost 필드 없어도 자동 각색)
            _run_crosspost(post)
        else:
            post["status"] = "failed"
            post["error"] = result.get("error", "unknown")
            logger.error(f"#{post_id} failed: {result.get('error')}")
            _notify_telegram(f"❌ 스레드 게시 실패 #{post_id}\n{result.get('error', 'unknown')}")

    save_queue(queue)

    # 게시 성공한 계정별로 SQUID 자동 댓글
    for acct in posted_accounts:
        _run_squid_engage(acct)


def _generate_crosspost(post: dict):
    """Threads 원본 텍스트에서 X/Reddit/LinkedIn 각색본 자동 생성.

    crosspost 필드가 없거나 비어있으면 Claude CLI로 생성.
    X는 글자수 초과 시에도 재생성.
    """
    import subprocess

    threads_text = post.get("text", "")
    first_reply = post.get("first_reply", "")
    crosspost = post.get("crosspost", {})
    post_id = post.get("id", "?")

    # X 글자수 체크
    def x_char_count(text):
        return sum(2 if ord(c) > 127 else 1 for c in text)

    need_generate = False
    if not crosspost:
        need_generate = True
    elif "x" not in crosspost or not crosspost.get("x", {}).get("text"):
        need_generate = True
    elif x_char_count(crosspost.get("x", {}).get("text", "")) > 280:
        need_generate = True
        logger.warning(f"#{post_id} X 글자수 초과, 재생성")

    if not need_generate:
        return  # 수동 각색본이 있고 글자수도 OK

    logger.info(f"#{post_id} crosspost 자동 각색 시작")

    prompt = f"""아래 Threads 원본 글을 X, Reddit, LinkedIn용으로 각색해줘.

## 원본 (Threads)
{threads_text}

## 각색 규칙

### X (한글, 반말, 임팩트)
- 한글 1자 = 2카운트, 영문/숫자/기호 = 1카운트 기준 **절대 270자 이내** (280자 제한이므로 여유 10자)
- 해시태그 없음, 이모지 0~1개
- 핵심만 남기고 압축. 임팩트 있게.

### Reddit (영어, casual, 토론형)
- title: 한 줄 제목 (영어)
- body: 영어 본문. 반말(casual). 마지막에 토론 유도 질문.
- subreddit: "artificial"
- reply: 영어 첫 댓글 (짧게, 개인 의견)

### LinkedIn (한글, 존댓말, 전문가)
- 존댓말로 변환. 전문가 톤.
- 해시태그 2~3개
- 마지막에 독자 참여 질문 (존댓말)

### 공통 CTA (첫 댓글/리플)
- X reply: "AI 소식 빠르게 보고 싶으면 팔로우! 같이 정보 나누자 👇 https://litt.ly/ambition_monkey"
- Reddit reply: 본문 관련 개인 의견 한 줄 (영어, 링크 없음)
- LinkedIn reply: "AI 관련 좋은 자료 빠르게 보고 싶으시면 팔로우 해주세요! 여기서 같이 정보 나눠요 👇 https://litt.ly/ambition_monkey"

## 출력 형식 (반드시 이 JSON만 출력, 다른 텍스트 없이)
```json
{{
  "x": {{"text": "...", "reply": "..."}},
  "reddit": {{"title": "...", "body": "...", "subreddit": "artificial", "reply": "..."}},
  "linkedin": {{"text": "...", "reply": "..."}}
}}
```"""

    try:
        claude_cmd = "/mnt/c/Users/hyuk/AppData/Roaming/npm/claude"
        result = subprocess.run(
            [claude_cmd, "-p", "--dangerously-skip-permissions", prompt],
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT, "CLAUDECODE": ""},
            timeout=120,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(f"#{post_id} crosspost 자동 각색 실패 (rc={result.returncode})")
            return

        # JSON 추출 (```json ... ``` 블록 또는 순수 JSON)
        import re
        output = result.stdout.strip()
        json_match = re.search(r'```json\s*\n(.*?)\n```', output, re.DOTALL)
        if json_match:
            output = json_match.group(1)
        else:
            # { 로 시작하는 부분 찾기
            idx = output.find('{')
            if idx >= 0:
                output = output[idx:]

        generated = json.loads(output)

        # X 글자수 최종 검증
        x_text = generated.get("x", {}).get("text", "")
        if x_char_count(x_text) > 280:
            logger.warning(f"#{post_id} X 자동 각색도 {x_char_count(x_text)}자 초과, 강제 트리밍")
            # 마지막 줄 제거하면서 280자 맞추기
            lines = x_text.split('\n')
            while x_char_count('\n'.join(lines)) > 280 and len(lines) > 1:
                lines.pop(-1)
            generated["x"]["text"] = '\n'.join(lines)

        post["crosspost"] = generated
        logger.info(f"#{post_id} crosspost 자동 각색 완료 (X: {x_char_count(generated['x']['text'])}자)")

    except json.JSONDecodeError as e:
        logger.warning(f"#{post_id} crosspost JSON 파싱 실패: {e}")
    except subprocess.TimeoutExpired:
        logger.warning(f"#{post_id} crosspost 자동 각색 타임아웃 (120s)")
    except Exception as e:
        logger.warning(f"#{post_id} crosspost 자동 각색 에러: {e}")


def _run_crosspost(post: dict):
    """Threads 게시 성공 후 X/Reddit/LinkedIn 크로스포스트.

    crosspost 필드가 없거나 X 글자수 초과 시 자동 각색 후 게시.
    한글 인코딩 문제로 cmd.exe 인자 대신 임시 JSON 파일로 전달.
    """
    import subprocess

    # 자동 각색 (필요 시)
    _generate_crosspost(post)

    WIN_PYTHON = r"C:\Users\hyuk\AppData\Local\Programs\Python\Python312\python.exe"
    TEMP_DIR = "/mnt/c/Users/hyuk/heysquid_sessions"
    crosspost = post.get("crosspost", {})
    post_id = post.get("id", "?")

    if not crosspost:
        logger.warning(f"#{post_id} crosspost 데이터 없음, 스킵")
        return

    for platform, cp in crosspost.items():
        try:
            # 임시 JSON 파일에 인자 저장 (UTF-8)
            args_file = os.path.join(TEMP_DIR, f"_crosspost_{platform}.json")
            with open(args_file, "w", encoding="utf-8") as f:
                json.dump(cp, f, ensure_ascii=False)
            win_args_file = args_file.replace("/mnt/c/", "C:\\\\").replace("/", "\\\\")

            if platform == "x":
                cmd = [
                    "/mnt/c/Windows/System32/cmd.exe", "/c", WIN_PYTHON,
                    r"C:\Users\hyuk\x_actions.py", "post-json",
                    win_args_file,
                ]
            elif platform == "reddit":
                cmd = [
                    "/mnt/c/Windows/System32/cmd.exe", "/c", WIN_PYTHON,
                    r"C:\Users\hyuk\reddit_actions.py", "post-json",
                    win_args_file,
                ]
            elif platform == "linkedin":
                cmd = [
                    "/mnt/c/Windows/System32/cmd.exe", "/c", WIN_PYTHON,
                    r"C:\Users\hyuk\crosspost.py", "linkedin-json",
                    win_args_file,
                ]
            else:
                continue

            logger.info(f"#{post_id} crosspost → {platform}")
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
            # cmd.exe stdout/stderr 디코딩 (cp949 fallback)
            try:
                stdout = proc.stdout.decode("utf-8")
            except UnicodeDecodeError:
                stdout = proc.stdout.decode("cp949", errors="replace")
            try:
                stderr = proc.stderr.decode("utf-8")
            except UnicodeDecodeError:
                stderr = proc.stderr.decode("cp949", errors="replace")

            # RESULT:{"ok":true,"post_url":"..."} 파싱
            for line in stdout.split('\n'):
                if line.startswith("RESULT:"):
                    r = json.loads(line[7:])
                    cp["status"] = "posted" if r.get("ok") else "failed"
                    if r.get("post_url"):
                        cp["post_url"] = r["post_url"]
                    if r.get("error"):
                        cp["error"] = r["error"]
                    break
            else:
                cp["status"] = "posted" if proc.returncode == 0 else "failed"

            status = cp.get("status", "unknown")
            url = cp.get("post_url", "")
            logger.info(f"#{post_id} {platform}: {status} {url}")
            _notify_telegram(f"{'✅' if status == 'posted' else '❌'} #{post_id} {platform} {status}\n{url}")

        except subprocess.TimeoutExpired:
            cp["status"] = "failed"
            cp["error"] = "timeout"
            logger.warning(f"#{post_id} {platform} timeout")
        except Exception as e:
            cp["status"] = "failed"
            cp["error"] = str(e)
            logger.warning(f"#{post_id} {platform} error: {e}")


def _run_squid_engage(account: str = "dkbsqd.official"):
    """collect + SQUID 댓글 작성 + post. Claude CLI -p 모드."""
    import subprocess

    engage_file = {
        "dkbsqd.official": "data/threads_engage.json",
        "ambition_monkey": "data/threads_engage_ambition.json",
    }.get(account, "data/threads_engage.json")

    # Step 1: collect
    try:
        subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, "threads_engage.py"), "collect", "--account", account, "--count", "10"],
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
            timeout=120,
        )
        logger.info(f"Engage collect completed ({account})")
    except Exception as e:
        logger.warning(f"Engage collect failed ({account}): {e}")
        return

    # Step 2: SQUID가 댓글 작성 + post (Claude CLI)
    try:
        claude_cmd = "/mnt/c/Users/hyuk/AppData/Roaming/npm/claude"
        prompt = (
            f"먼저 heysquid/skills/threads_fortune/_engage_persona.py를 읽어서 {account} 페르소나를 확인해. "
            f"그 다음 {engage_file}을 읽어. 10개 글이 있어. "
            "각 글의 text를 직접 읽고, 해당 계정 페르소나로 공감 댓글을 직접 작성해. "
            "일반 글이면 순수 공감만 (1~2줄, ㅋㅋ 자연스럽게). "
            "AI/테크 글이면 인사이트 살짝 섞어도 돼. "
            "사주 관련 글이면 사주 살짝 섞어도 돼. "
            "봇 티 나면 안 돼. 홍보/CTA 절대 안 함. "
            "각 글의 comment 필드에 채운 후 JSON 저장하고, "
            f"PYTHONPATH=. python3 scripts/threads_engage.py post --account {account} 실행해서 댓글 달아."
        )
        result = subprocess.run(
            [claude_cmd, "-p", "--dangerously-skip-permissions", prompt],
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT, "CLAUDECODE": ""},
            timeout=600,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            logger.info(f"SQUID engage completed successfully ({account})")
        else:
            logger.warning(f"SQUID engage failed ({account}, rc={result.returncode}): {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        logger.warning(f"SQUID engage timed out ({account}, 600s)")
    except Exception as e:
        logger.warning(f"SQUID engage failed ({account}): {e}")


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


def cmd_add(text: str, time_str: str, first_reply: str = None, account: str = None, topic: str = None):
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
        "topic": topic,
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
