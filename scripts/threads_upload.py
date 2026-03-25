"""
Threads 게시물 업로드 자동화
- Playwright Chromium + persistent context (세션 영구 저장)

사용법:
  # 최초 로그인 (브라우저 열려서 수동 로그인)
  python3 scripts/threads_upload.py --login

  # 텍스트 게시
  python3 scripts/threads_upload.py "게시할 텍스트"

  # 이미지 + 텍스트
  python3 scripts/threads_upload.py --image /path/to/image.jpg "텍스트"

  # 미리보기만 (게시 안 함)
  python3 scripts/threads_upload.py --dry-run "테스트"
"""

import argparse
import os
import sys
import time

from playwright.sync_api import sync_playwright

BROWSER_DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "threads_browser_data",
)


def clean_locks():
    """브라우저 lock 파일 제거."""
    for name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        path = os.path.join(BROWSER_DATA, name)
        if os.path.exists(path):
            os.remove(path)


def create_context(playwright, headless=False):
    """persistent context 생성."""
    os.makedirs(BROWSER_DATA, exist_ok=True)
    clean_locks()
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


def navigate_to_threads(page):
    """Threads 메인으로 이동 + 로그인 확인."""
    page.goto("https://www.threads.net/", timeout=30000)
    time.sleep(5)

    # "What's new?" 또는 Post 버튼이 있으면 로그인 된 것
    post_btn = page.query_selector('div[role="button"]:has-text("Post")')
    whatsnew = page.query_selector('[placeholder*="new"]')
    if post_btn or whatsnew:
        print("로그인 확인 OK", flush=True)
        return True

    print("로그인 안 됨. --login으로 먼저 로그인하세요.", flush=True)
    return False


def open_compose(page):
    """새 글 작성 모달 열기."""
    # "What's new?" 텍스트 영역 클릭
    whatsnew = page.query_selector('[contenteditable="true"]')
    if whatsnew:
        whatsnew.click()
        time.sleep(2)
        print("글쓰기 영역 활성화!", flush=True)
        return True

    # + 버튼 또는 Create 버튼
    for selector in [
        '[aria-label="Create"]',
        '[aria-label="새로운 스레드"]',
        '[aria-label="New thread"]',
    ]:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                time.sleep(2)
                print("글쓰기 모달 열기!", flush=True)
                return True
        except Exception:
            continue

    print("글쓰기 영역을 찾을 수 없습니다.", flush=True)
    return False


def type_text(page, text: str):
    """텍스트 입력."""
    for selector in [
        '[contenteditable="true"]',
        'div[role="textbox"]',
        'p[data-placeholder]',
    ]:
        try:
            el = page.wait_for_selector(selector, timeout=5000)
            if el:
                el.click()
                time.sleep(0.5)
                page.keyboard.type(text, delay=30)
                print(f"텍스트 입력 완료 ({len(text)}자)", flush=True)
                time.sleep(1)
                return True
        except Exception:
            continue

    print("텍스트 입력 영역을 찾을 수 없습니다.", flush=True)
    return False


def attach_image(page, image_path: str):
    """이미지 첨부."""
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        print(f"이미지 파일 없음: {abs_path}", flush=True)
        return False

    print(f"이미지 첨부: {abs_path}", flush=True)

    # hidden file input 찾기
    try:
        file_input = page.query_selector('input[type="file"]')
        if file_input:
            file_input.set_input_files(abs_path)
            print("이미지 첨부 완료!", flush=True)
            time.sleep(3)
            return True
    except Exception:
        pass

    # 첨부 버튼 클릭
    for selector in [
        '[aria-label="Attach media"]',
        '[aria-label="미디어 첨부"]',
    ]:
        try:
            btn = page.query_selector(selector)
            if btn:
                btn.click()
                time.sleep(1)
                file_input = page.wait_for_selector(
                    'input[type="file"]', timeout=5000
                )
                if file_input:
                    file_input.set_input_files(abs_path)
                    print("이미지 첨부 완료!", flush=True)
                    time.sleep(3)
                    return True
        except Exception:
            continue

    print("이미지 첨부 실패.", flush=True)
    return False


def click_post(page):
    """게시 버튼 클릭 — 모달 안의 Post 버튼 (Cancel 옆)."""
    # 모달에는 Cancel과 Post가 함께 있음. Cancel 근처의 Post를 찾는다.
    buttons = page.query_selector_all('div[role="button"]')
    found_cancel = False
    for btn in buttons:
        try:
            text = btn.inner_text().strip()
            if text == "Cancel" or text == "취소":
                found_cancel = True
                continue
            if found_cancel and text in ("Post", "게시") and btn.is_visible():
                btn.click()
                print("게시 버튼 클릭!", flush=True)
                time.sleep(5)
                return True
        except Exception:
            continue

    print("게시 버튼을 찾을 수 없습니다.", flush=True)
    return False


def do_login():
    """수동 로그인 모드."""
    with sync_playwright() as p:
        context = create_context(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.threads.net/login", timeout=30000)
        print("Chromium 창에서 로그인해주세요.", flush=True)
        print("로그인 완료 후 Enter를 누르세요...", flush=True)
        input()
        context.close()
    print("세션 저장 완료!", flush=True)


def upload_thread(text: str, image_path: str | None = None, dry_run: bool = False):
    """메인 업로드 함수."""
    with sync_playwright() as p:
        context = create_context(p, headless=False)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            if not navigate_to_threads(page):
                return False

            if not open_compose(page):
                return False

            if not type_text(page, text):
                return False

            if image_path and not attach_image(page, image_path):
                print("이미지 첨부 실패, 텍스트만 게시 시도...", flush=True)

            if dry_run:
                print("\n[DRY RUN] 게시하지 않고 종료합니다.", flush=True)
                page.screenshot(path="/tmp/threads_dryrun.png")
                print("스크린샷: /tmp/threads_dryrun.png", flush=True)
                time.sleep(3)
                return True

            if not click_post(page):
                print("게시 실패.", flush=True)
                return False

            print("게시 완료!", flush=True)
            return True

        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="Threads 게시물 업로드")
    parser.add_argument("text", nargs="?", help="게시할 텍스트")
    parser.add_argument("--image", "-i", help="첨부할 이미지 경로")
    parser.add_argument("--login", action="store_true", help="로그인 모드")
    parser.add_argument(
        "--dry-run", action="store_true", help="게시하지 않고 미리보기만"
    )
    args = parser.parse_args()

    if args.login:
        do_login()
        return

    if not args.text:
        parser.error("게시할 텍스트를 입력하세요 (또는 --login으로 먼저 로그인)")

    success = upload_thread(args.text, args.image, args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
