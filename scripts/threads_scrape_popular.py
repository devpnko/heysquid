"""
Threads 홈피드 + 레퍼런스 계정 인기글 수집 스크립트
- Playwright headful Chromium 사용
- 세션: data/threads_storage.json
- 결과: /tmp/threads_popular_posts.json
"""

import json
import re
import time
import sys

from playwright.sync_api import sync_playwright

STORAGE_PATH = "/Users/hyuk/heysquid/data/threads_storage.json"
OUTPUT_PATH = "/tmp/threads_popular_posts.json"

REFERENCE_ACCOUNTS = [
    "choi.openai",
    "smart_daddy_ai",
    "since_1985_love",
    "leosofts2016",
]


def extract_username_from_container(container) -> str:
    """컨테이너에서 작성자 유저네임 추출."""
    # /@username 패턴 링크에서 추출 (post/ 없는 것이 프로필 링크)
    links = container.query_selector_all("a[href]")
    for link in links:
        href = link.get_attribute("href") or ""
        # /@username 형태 (post/, media, replies 등 제외)
        m = re.match(r"^/@([^/]+)$", href)
        if m:
            return "@" + m.group(1)
    return ""


def extract_text_from_container(container) -> str:
    """컨테이너에서 본문 텍스트 추출."""
    full_text = container.inner_text()
    lines = full_text.split("\n")

    # 시간 패턴: "N분", "N시간", "N일", "N주", "방금", "YYYY-MM-DD"
    time_pattern = re.compile(
        r"^(\d+[분시일주]|방금|\d+[mhd]w?|just now|\d{4}-\d{2}-\d{2})$",
        re.IGNORECASE,
    )
    # 숫자만 있는 줄 (좋아요수, 답글수 등) — "/" 포함 슬라이드 인디케이터도
    num_pattern = re.compile(r"^[\d,./]+$")
    # 리포스트 알림 줄
    repost_pattern = re.compile(r"님이 .+ 리포스트함")
    # 팔로우/팔로잉
    follow_pattern = re.compile(r"^(팔로우|팔로잉)$")
    # 고정됨 표시
    pinned_pattern = re.compile(r"^고정됨$")
    # URL 줄 (도메인 패턴)
    url_pattern = re.compile(r"^https?://|\.com|\.kr|\.net|\.io")
    # 해시태그 전용 줄 (단어만 있거나 해시태그 링크 텍스트)
    # 예: "AI Threads", "바이브코딩 Vibe coding", "클로드코드"
    # → 이런 줄은 시간 패턴 직전에 나오는 태그 라벨이므로 건너뜀
    # 시간 이후에 나오면 본문으로 취급

    content_lines = []
    state = "before_time"  # before_time → collecting

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if pinned_pattern.match(stripped):
            continue
        if repost_pattern.search(stripped):
            continue
        if follow_pattern.match(stripped):
            continue

        if state == "before_time":
            if time_pattern.match(stripped):
                state = "collecting"
            # username, 해시태그 라벨, 날짜 등 시간 이전은 건너뜀
            continue

        if state == "collecting":
            if num_pattern.match(stripped):
                # 숫자만 나오면 본문 끝
                break
            # URL이나 도메인 줄은 건너뜀
            if url_pattern.search(stripped) and len(stripped) < 60:
                continue
            content_lines.append(stripped)

    text = "\n".join(content_lines).strip()
    return text


def extract_counts_from_container(container) -> tuple[str, str]:
    """컨테이너에서 좋아요 수와 답글 수 추출.

    Threads 홈피드 구조:
    - 좋아요/답글 수가 숫자 span으로만 표시됨 (aria-label 없음)
    - 컨테이너 전체 텍스트의 마지막 숫자들이 좋아요/답글
    """
    full_text = container.inner_text()
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # 숫자만 있는 줄들을 마지막에서 수집
    num_pattern = re.compile(r"^[\d,]+$")
    trailing_nums = []
    for line in reversed(lines):
        if num_pattern.match(line):
            trailing_nums.insert(0, line.replace(",", ""))
        else:
            break

    # 슬라이드(1/5 등)는 제외
    slash_pattern = re.compile(r"^\d+/\d+$")
    trailing_nums = [n for n in trailing_nums if not slash_pattern.match(n)]

    # Threads: 순서는 일반적으로 [좋아요, 답글, 리포스트, 인용] 또는 [답글, 좋아요]
    # 실제로는 컨테이너 텍스트 마지막 부분의 숫자 순서가 다를 수 있음
    # 경험상 첫 번째 = 좋아요, 두 번째 = 답글 (또는 반대)
    # 더 안전하게: aria-label 버튼 시도

    # 버튼에서 aria-label 시도
    likes = "0"
    replies = "0"
    buttons = container.query_selector_all("button[aria-label]")
    for btn in buttons:
        label = (btn.get_attribute("aria-label") or "").lower()
        if "좋아요" in label or "like" in label:
            m = re.search(r"([\d,]+)", label)
            if m:
                likes = m.group(1).replace(",", "")
        elif "답글" in label or "repl" in label:
            m = re.search(r"([\d,]+)", label)
            if m:
                replies = m.group(1).replace(",", "")

    # aria-label에서 못 가져왔으면 trailing_nums 사용
    if likes == "0" and trailing_nums:
        likes = trailing_nums[0] if trailing_nums else "0"
    if replies == "0" and len(trailing_nums) > 1:
        replies = trailing_nums[1]

    return likes, replies


def scroll_and_collect(page, source: str, target_count: int = 20) -> list[dict]:
    """페이지를 스크롤하면서 포스트를 target_count개 수집."""
    posts = []
    seen_texts = set()
    max_scrolls = 40
    scroll_count = 0
    prev_count = 0
    stale_count = 0

    print(f"[{source}] 수집 시작 (목표: {target_count}개)...", flush=True)

    while len(posts) < target_count and scroll_count < max_scrolls:
        containers = page.query_selector_all("div[data-pressable-container]")

        for container in containers:
            if len(posts) >= target_count:
                break

            try:
                username = extract_username_from_container(container)
                text = extract_text_from_container(container)

                if not text or not username:
                    continue

                # 중복 제거 (유저네임 + 텍스트 첫 40자)
                dedup_key = username + "::" + text[:40]
                if dedup_key in seen_texts:
                    continue
                seen_texts.add(dedup_key)

                likes, replies = extract_counts_from_container(container)

                posts.append({
                    "username": username,
                    "text": text[:600],
                    "likes": likes,
                    "replies": replies,
                    "source": source,
                })
                print(f"  [{len(posts)}] {username}: {text[:60].replace(chr(10), ' ')}...", flush=True)

            except Exception as e:
                pass

        if len(posts) >= target_count:
            break

        # 새 포스트가 추가되지 않으면 staleness 카운트 증가
        if len(posts) == prev_count:
            stale_count += 1
        else:
            stale_count = 0
        prev_count = len(posts)

        # 3번 연속 새 포스트 없으면 더 적극적인 스크롤 시도
        if stale_count >= 3 and scroll_count < max_scrolls - 5:
            # 페이지 끝까지 이동 후 대기
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
            stale_count = 0
        else:
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)

        scroll_count += 1

    print(f"[{source}] 수집 완료: {len(posts)}개 (스크롤 {scroll_count}회)", flush=True)
    return posts


def scrape_homefeed(page) -> list[dict]:
    """threads.com 홈피드 수집."""
    print("\n[홈피드] threads.com 접속 중...", flush=True)
    page.goto("https://www.threads.com/", timeout=30000)

    # 로그인 확인 대기
    try:
        page.wait_for_selector("div[data-pressable-container]", timeout=15000)
    except Exception:
        print("[홈피드] 포스트 로드 실패 — 로그인 필요하거나 페이지 오류", flush=True)
        # 현재 URL 확인
        print(f"  현재 URL: {page.url}", flush=True)
        return []

    time.sleep(2)
    return scroll_and_collect(page, "homefeed", target_count=20)


def scrape_profile(page, username: str) -> list[dict]:
    """특정 계정 프로필 페이지 수집."""
    url = f"https://www.threads.com/@{username}"
    print(f"\n[프로필] @{username} 접속 중...", flush=True)

    try:
        page.goto(url, timeout=30000)
    except Exception as e:
        print(f"[프로필] 페이지 이동 실패: {e}", flush=True)
        return []

    # 프로필 페이지 로드 대기
    try:
        page.wait_for_selector("div[data-pressable-container]", timeout=15000)
    except Exception:
        # 404 또는 비공개 계정
        title = page.title()
        print(f"[프로필] @{username} — 포스트 없음 (title={title!r})", flush=True)
        return []

    time.sleep(2)
    posts = scroll_and_collect(page, f"profile:{username}", target_count=5)
    return posts


def main():
    all_posts = []

    with sync_playwright() as p:
        print("Playwright Chromium 시작 (headful)...", flush=True)
        browser = p.chromium.launch(
            headless=False,
            args=["--window-size=1280,900", "--disable-blink-features=AutomationControlled"],
        )

        # 저장된 세션으로 컨텍스트 생성
        try:
            with open(STORAGE_PATH) as f:
                storage_state = json.load(f)
            context = browser.new_context(
                storage_state=storage_state,
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            print("저장된 세션 로드 완료.", flush=True)
        except Exception as e:
            print(f"세션 로드 실패: {e} — 신규 컨텍스트 생성", flush=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})

        page = context.new_page()

        # 1. 홈피드 수집
        homefeed_posts = scrape_homefeed(page)
        all_posts.extend(homefeed_posts)

        # 2. 레퍼런스 계정 수집
        for account in REFERENCE_ACCOUNTS:
            profile_posts = scrape_profile(page, account)
            all_posts.extend(profile_posts)
            time.sleep(2)

        # 세션 저장 (갱신)
        try:
            updated_storage = context.storage_state()
            with open(STORAGE_PATH, "w") as f:
                json.dump(updated_storage, f, ensure_ascii=False, indent=2)
            print("\n세션 저장 완료.", flush=True)
        except Exception as e:
            print(f"세션 저장 실패: {e}", flush=True)

        browser.close()

    # 결과 저장
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"\n총 {len(all_posts)}개 포스트 수집 완료 → {OUTPUT_PATH}", flush=True)
    print_results(all_posts)
    return all_posts


def print_results(posts: list[dict]):
    print("\n" + "=" * 70, flush=True)
    print(f"수집된 글 목록 (총 {len(posts)}개)", flush=True)
    print("=" * 70, flush=True)

    for i, post in enumerate(posts, 1):
        src_label = {
            "homefeed": "홈피드",
        }.get(post["source"], post["source"].replace("profile:", "@"))
        print(f"\n[{i}] {post['username']}  ({src_label})", flush=True)
        print(f"    좋아요 {post['likes']}  |  답글 {post['replies']}", flush=True)
        print(f"    {post['text'][:300]}", flush=True)
        print("    " + "-" * 50, flush=True)


if __name__ == "__main__":
    main()
