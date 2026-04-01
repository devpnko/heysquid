"""
Threads 홈피드 공감 댓글 자동화
- Step 1: 홈피드에서 글 + URL 수집 → JSON 저장
- Step 2: SQUID가 댓글 작성 → JSON에 댓글 추가
- Step 3: URL로 직접 가서 댓글 달기

사용법:
  python3 scripts/threads_engage.py collect          # 홈피드 글 10개 수집
  python3 scripts/threads_engage.py collect --count 5 # 5개만
  python3 scripts/threads_engage.py post              # 작성된 댓글 게시
  python3 scripts/threads_engage.py post --dry-run    # 게시 미리보기
"""

import argparse
import json
import os
import random
import sys
import time

from playwright.sync_api import sync_playwright

BROWSER_DATA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "threads_browser_data",
)
ENGAGE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "threads_engage.json",
)

MY_USERNAME = "dkbsqd.official"


def clean_locks():
    for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        path = os.path.join(BROWSER_DATA, name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def create_context(playwright):
    clean_locks()
    return playwright.chromium.launch_persistent_context(
        BROWSER_DATA,
        headless=True,
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


# ── Step 1: 수집 ──────────────────────────────────────────

def cmd_collect(count: int = 10):
    """홈피드에서 글 텍스트 + URL 수집 → JSON 저장."""
    with sync_playwright() as p:
        context = create_context(p)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            page.goto("https://www.threads.net/", timeout=30000)
            time.sleep(5)

            posts = []
            seen_urls = set()

            for scroll in range(count * 3):
                if len(posts) >= count:
                    break

                links = page.evaluate("""() => {
                    const results = [];
                    document.querySelectorAll('div[data-pressable-container]').forEach(el => {
                        const text = el.innerText || '';
                        const anchors = el.querySelectorAll('a[href*="/post/"]');
                        if (anchors.length > 0) {
                            results.push({url: anchors[0].href, text: text});
                        }
                    });
                    return results;
                }""")

                for link in links:
                    if len(posts) >= count:
                        break
                    url = link["url"]
                    text = link["text"].strip()

                    if MY_USERNAME in text:
                        continue
                    if url in seen_urls:
                        continue
                    if len(text) < 30:
                        continue

                    seen_urls.add(url)

                    # username 추출
                    username = ""
                    try:
                        parts = url.split("/@")
                        if len(parts) > 1:
                            username = parts[1].split("/")[0]
                    except:
                        pass

                    posts.append({
                        "url": url,
                        "username": username,
                        "text": text[:500],
                        "comment": "",  # SQUID가 채울 부분
                        "status": "pending",
                    })

                page.mouse.wheel(0, 700)
                time.sleep(2)

            # JSON 저장
            with open(ENGAGE_FILE, "w", encoding="utf-8") as f:
                json.dump({"posts": posts}, f, ensure_ascii=False, indent=2)

            print(f"✅ {len(posts)}개 수집 → {ENGAGE_FILE}")
            print()
            for i, p in enumerate(posts):
                preview = p["text"][:80].replace("\n", " ")
                print(f"[{i+1}] @{p['username']}: {preview}...")
                print(f"    {p['url']}")
                print()

        finally:
            context.close()


# ── Step 3: 게시 ──────────────────────────────────────────

def cmd_post(dry_run: bool = False):
    """작성된 댓글을 URL로 가서 달기."""
    if not os.path.exists(ENGAGE_FILE):
        print(f"수집 파일 없음. 먼저 collect 하세요.")
        return

    with open(ENGAGE_FILE, encoding="utf-8") as f:
        data = json.load(f)

    posts = [p for p in data["posts"] if p.get("comment") and p["status"] == "pending"]

    if not posts:
        print("댓글이 작성된 pending 게시물이 없습니다.")
        print("SQUID가 threads_engage.json의 comment 필드를 채워야 합니다.")
        return

    print(f"게시할 댓글: {len(posts)}개\n")

    if dry_run:
        for i, p in enumerate(posts):
            preview = p["text"][:60].replace("\n", " ")
            print(f"[{i+1}] @{p['username']}: {preview}...")
            print(f"  댓글: {p['comment']}")
            print()
        print(f"[DRY RUN] {len(posts)}개 미리보기 완료")
        return

    with sync_playwright() as pw:
        context = create_context(pw)
        page = context.pages[0] if context.pages else context.new_page()

        try:
            success = 0
            for i, p in enumerate(posts):
                preview = p["text"][:60].replace("\n", " ")
                print(f"\n[{i+1}/{len(posts)}] @{p['username']}: {preview}...")
                print(f"  댓글: {p['comment']}", flush=True)

                try:
                    # URL로 직접 이동
                    page.goto(p["url"], timeout=30000)
                    time.sleep(4)

                    # 좋아요 누르기
                    liked = False
                    for sel in ('svg[aria-label="Like"]', 'svg[aria-label="좋아요"]'):
                        like_btn = page.query_selector(sel)
                        if like_btn:
                            like_btn.click()
                            time.sleep(1)
                            liked = True
                            print("  ❤️ 좋아요", flush=True)
                            break

                    # Reply 아이콘 클릭
                    replied = False
                    for sel in ('svg[aria-label="Reply"]', 'svg[aria-label="답글"]'):
                        btn = page.query_selector(sel)
                        if btn:
                            btn.click()
                            time.sleep(2)
                            replied = True
                            break

                    if not replied:
                        print("  ❌ Reply 버튼 못 찾음", flush=True)
                        continue

                    # 입력
                    editor = page.wait_for_selector('[contenteditable="true"]', timeout=5000)
                    if not editor:
                        print("  ❌ 입력창 못 찾음", flush=True)
                        page.keyboard.press("Escape")
                        continue

                    editor.click()
                    time.sleep(0.3)
                    page.keyboard.type(p["comment"], delay=40)
                    time.sleep(1)

                    # Post 버튼 — Cancel 모달 안에서 마지막 Post 찾기
                    time.sleep(1)
                    posted = False
                    # 방법1: 모달 안의 Post 버튼 직접 찾기
                    post_btns = page.query_selector_all('div[role="button"]')
                    target = None
                    for btn in reversed(post_btns):
                        try:
                            txt = btn.inner_text().strip()
                            if txt in ("Post", "게시") and btn.is_visible():
                                target = btn
                                break
                        except:
                            continue
                    if target:
                        target.click()
                        time.sleep(4)
                        posted = True

                    if posted:
                        # 내 댓글에 좋아요 누르기 — 가장 마지막 Like 버튼이 내 댓글
                        time.sleep(2)
                        try:
                            like_btns = page.query_selector_all('svg[aria-label="Like"], svg[aria-label="좋아요"]')
                            if like_btns:
                                like_btns[-1].click()
                                time.sleep(1)
                                print("  ❤️ 내 댓글 좋아요", flush=True)
                        except Exception:
                            pass
                        print("  ✅ 완료!", flush=True)
                        p["status"] = "done"
                        success += 1
                    else:
                        print("  ❌ Post 못 찾음", flush=True)
                        page.keyboard.press("Escape")

                    # 랜덤 딜레이
                    time.sleep(random.uniform(3, 6))

                except Exception as e:
                    print(f"  에러: {e}", flush=True)

            # 결과 저장
            with open(ENGAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"\n완료: {success}/{len(posts)}개 성공")

        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="Threads 공감 댓글")
    parser.add_argument("action", choices=["collect", "post"], help="collect: 수집, post: 게시")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.action == "collect":
        cmd_collect(args.count)
    elif args.action == "post":
        cmd_post(args.dry_run)


if __name__ == "__main__":
    main()
