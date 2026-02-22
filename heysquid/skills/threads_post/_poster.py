"""Threads 예약 게시 — Playwright 기반 자동 게시 모듈.

threads_schedule.json에서 예정 시간이 된 글을 찾아 Playwright로 게시.
"""

import json
import logging
import os
import time
import asyncio
from datetime import datetime

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_FILE = os.path.join(DATA_DIR, "threads_storage.json")
SCHEDULE_FILE = os.path.join(DATA_DIR, "threads_schedule.json")
LOCK_FILE = os.path.join(DATA_DIR, "threads_post.lock")
THREADS_URL = "https://www.threads.net"


def _acquire_lock() -> bool:
    """게시 중복 방지 락. 5분 지나면 stale로 판단."""
    if os.path.exists(LOCK_FILE):
        age = time.time() - os.path.getmtime(LOCK_FILE)
        if age < 300:
            return False
        os.remove(LOCK_FILE)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))
    return True


def _release_lock():
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


async def _post_thread_playwright(text: str) -> dict:
    """Playwright로 Threads에 글 게시."""
    if not os.path.exists(STORAGE_FILE):
        return {"success": False, "error": "세션 파일 없음 (threads_storage.json)"}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context(
            storage_state=STORAGE_FILE,
            viewport={"width": 430, "height": 932},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()
        try:
            await page.goto(THREADS_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            # "만들기" 버튼 (.nth(1)로 사이드바/메인 구분)
            create_btn = page.get_by_role("button", name="만들기")
            count = await create_btn.count()
            if count > 1:
                await create_btn.nth(1).click()
            else:
                await create_btn.first.click()
            await page.wait_for_timeout(2000)

            # 텍스트 입력 (contenteditable)
            editor = page.locator('[contenteditable="true"]')
            await editor.first.click()
            await page.wait_for_timeout(500)
            await page.keyboard.type(text, delay=10)
            await page.wait_for_timeout(1000)

            # "게시" 버튼 (visible한 것만 클릭)
            post_buttons = await page.get_by_role("button", name="게시", exact=True).all()
            posted = False
            for btn in post_buttons:
                if await btn.is_visible():
                    await btn.click()
                    posted = True
                    break

            if not posted:
                # 영어 UI fallback
                post_buttons_en = await page.get_by_role("button", name="Post", exact=True).all()
                for btn in post_buttons_en:
                    if await btn.is_visible():
                        await btn.click()
                        posted = True
                        break

            if not posted:
                return {"success": False, "error": "게시 버튼을 찾을 수 없음"}

            await page.wait_for_timeout(5000)

            # 세션 저장
            storage = await context.storage_state()
            with open(STORAGE_FILE, "w") as f:
                json.dump(storage, f)

            return {"success": True, "error": None}

        except Exception as e:
            return {"success": False, "error": str(e)}
        finally:
            await browser.close()


def post_thread(text: str) -> dict:
    """동기 래퍼."""
    return asyncio.run(_post_thread_playwright(text))


def check_and_post_due() -> list[dict]:
    """threads_schedule.json에서 예정 시간이 된 글을 찾아 게시.

    Returns:
        list[dict]: 게시 결과 [{id, title, success, error}, ...]
                    게시할 글이 없으면 빈 리스트.
    """
    if not os.path.exists(SCHEDULE_FILE):
        return []

    if not _acquire_lock():
        logger.info("다른 게시 프로세스가 실행 중, 스킵")
        return []

    try:
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        now = datetime.now()
        results = []
        modified = False

        for post in data.get("scheduled_posts", []):
            if post.get("status") != "scheduled":
                continue
            if not post.get("text"):
                continue

            scheduled_time = datetime.strptime(post["scheduled_time"], "%Y-%m-%d %H:%M")
            if scheduled_time > now:
                continue

            # 시간이 됨 — 게시
            logger.info(f"예약 게시 시작: #{post['id']} '{post['title']}'")
            result = post_thread(post["text"])

            if result["success"]:
                post["status"] = "posted"
                post["posted_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
                modified = True
                logger.info(f"게시 성공: #{post['id']}")
            else:
                post["status"] = "failed"
                post["error"] = result.get("error", "")[:200]
                modified = True
                logger.error(f"게시 실패: #{post['id']} — {result['error']}")

            results.append({
                "id": post["id"],
                "title": post["title"],
                **result,
            })

        if modified:
            with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        return results

    finally:
        _release_lock()
