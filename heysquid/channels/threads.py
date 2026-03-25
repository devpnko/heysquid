"""
Threads channel adapter — heysquid

Posts to Threads using Playwright browser automation.
Persistent context maintains login session across runs.

Setup:
    1. python3 scripts/threads_upload.py --login  (최초 1회)
    2. 이후 자동으로 세션 재사용
"""

import logging
import os
import time

from ._base import ChannelAdapter
from ..config import PROJECT_ROOT

logger = logging.getLogger(__name__)

BROWSER_DATA = os.path.join(PROJECT_ROOT, "data", "threads_browser_data")


def _clean_locks():
    """Remove stale browser lock files."""
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(BROWSER_DATA, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def _create_context(playwright, headless=True):
    """Create persistent browser context with saved session."""
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
    """Check if logged in by looking for the compose area."""
    post_btn = page.query_selector('div[role="button"]:has-text("Post")')
    whatsnew = page.query_selector('[placeholder*="new"]')
    return bool(post_btn or whatsnew)


def _open_compose(page) -> bool:
    """Open the new thread compose modal."""
    # Try "What's new?" area first
    whatsnew = page.query_selector('[contenteditable="true"]')
    if whatsnew:
        whatsnew.click()
        time.sleep(2)
        return True

    # Try Create button
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
    """Type text into the compose area."""
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
    """Click the Post button inside the compose modal."""
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
    """Post a first reply (comment) to the just-posted thread.

    Flow:
    1. Navigate to own profile
    2. Click latest post to open detail
    3. Click 💬 (Reply) icon to open reply modal
    4. Type reply text
    5. Click Post button in modal
    """
    time.sleep(3)

    # Step 1: Go to own profile to find the latest post
    page.goto("https://www.threads.net/@dkbsqd.official", timeout=30000)
    time.sleep(5)

    # Step 2: Click the first (latest) post
    posts = page.query_selector_all("div[data-pressable-container]")
    if not posts:
        return False
    posts[0].click()
    time.sleep(5)

    # Step 3: Click 💬 Reply icon
    for selector in (
        'svg[aria-label="Reply"]',
        'svg[aria-label="답글"]',
        'svg[aria-label="Comment"]',
    ):
        btn = page.query_selector(selector)
        if btn:
            btn.click()
            time.sleep(3)
            break
    else:
        return False

    # Step 4: Type reply text
    try:
        el = page.wait_for_selector('[contenteditable="true"]', timeout=5000)
        if not el:
            return False
        el.click()
        time.sleep(0.5)
        page.keyboard.type(reply_text, delay=30)
        time.sleep(1)
    except Exception:
        return False

    # Step 5: Click Post button (Cancel 뒤에 오는 Post)
    buttons = page.query_selector_all('div[role="button"]')
    found_cancel = False
    for btn in buttons:
        try:
            txt = btn.inner_text().strip()
            if txt in ("Cancel", "취소"):
                found_cancel = True
                continue
            if found_cancel and txt in ("Post", "게시") and btn.is_visible():
                btn.click()
                time.sleep(5)
                return True
        except Exception:
            continue
    return False


class ThreadsChannel(ChannelAdapter):
    """Playwright-based Threads channel adapter."""

    def send_message(self, chat_id, text, **kwargs):
        """Post text to Threads via Playwright.

        Args:
            chat_id: Ignored (posts to own account)
            text: Post content (500 chars recommended)
            first_reply: Optional first comment text (kwargs)
            headless: Run headless (default True) (kwargs)

        Returns:
            dict: {"ok": bool, "error": str | None}
        """
        first_reply = kwargs.get("first_reply")
        headless = kwargs.get("headless", False)

        if not os.path.exists(BROWSER_DATA):
            return {
                "ok": False,
                "error": "No browser session. Run: python3 scripts/threads_upload.py --login",
            }

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"ok": False, "error": "playwright not installed"}

        try:
            with sync_playwright() as p:
                context = _create_context(p, headless=headless)
                page = context.pages[0] if context.pages else context.new_page()

                try:
                    # Navigate to Threads
                    page.goto("https://www.threads.net/", timeout=30000)
                    time.sleep(5)

                    if not _is_logged_in(page):
                        return {
                            "ok": False,
                            "error": "Not logged in. Run: python3 scripts/threads_upload.py --login",
                        }

                    if not _open_compose(page):
                        return {"ok": False, "error": "Failed to open compose"}

                    if not _type_text(page, text):
                        return {"ok": False, "error": "Failed to type text"}

                    if not _click_post(page):
                        return {"ok": False, "error": "Failed to click Post button"}

                    logger.info(f"[Threads] Posted: {text[:60]}...")

                    # First reply (CTA comment)
                    if first_reply:
                        if _post_first_reply(page, first_reply):
                            logger.info(f"[Threads] First reply posted: {first_reply[:40]}...")
                        else:
                            logger.warning("[Threads] First reply failed")

                    return {"ok": True}

                finally:
                    context.close()

        except Exception as e:
            logger.error(f"[Threads] Post error: {e}")
            return {"ok": False, "error": str(e)}

    def send_file(self, chat_id, file_path, **kwargs):
        """Post with image attachment.

        Args:
            chat_id: Ignored
            file_path: Path to image file
            text: Post text (kwargs, required)
        """
        text = kwargs.get("text", "")
        if not text:
            return {"ok": False, "error": "text is required for image posts"}

        headless = kwargs.get("headless", False)
        first_reply = kwargs.get("first_reply")

        if not os.path.exists(file_path):
            return {"ok": False, "error": f"File not found: {file_path}"}

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return {"ok": False, "error": "playwright not installed"}

        try:
            with sync_playwright() as p:
                context = _create_context(p, headless=headless)
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

                    # Attach image
                    abs_path = os.path.abspath(file_path)
                    attached = False
                    try:
                        file_input = page.query_selector('input[type="file"]')
                        if file_input:
                            file_input.set_input_files(abs_path)
                            time.sleep(3)
                            attached = True
                    except Exception:
                        pass

                    if not attached:
                        for sel in ('[aria-label="Attach media"]', '[aria-label="미디어 첨부"]'):
                            try:
                                btn = page.query_selector(sel)
                                if btn:
                                    btn.click()
                                    time.sleep(1)
                                    fi = page.wait_for_selector('input[type="file"]', timeout=5000)
                                    if fi:
                                        fi.set_input_files(abs_path)
                                        time.sleep(3)
                                        attached = True
                                        break
                            except Exception:
                                continue

                    if not attached:
                        logger.warning("[Threads] Image attach failed, posting text only")

                    if not _click_post(page):
                        return {"ok": False, "error": "Failed to click Post button"}

                    logger.info(f"[Threads] Posted with image: {text[:60]}...")

                    if first_reply:
                        _post_first_reply(page, first_reply)

                    return {"ok": True}

                finally:
                    context.close()

        except Exception as e:
            logger.error(f"[Threads] Post error: {e}")
            return {"ok": False, "error": str(e)}
