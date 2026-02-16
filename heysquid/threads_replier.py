"""
Threads 답글 모듈 -- Playwright 기반

세션 파일(data/threads_storage.json)로 로그인 유지,
홈피드 게시물을 읽고, 특정 사용자의 프로필에서 답글을 단다.
"""

import os
import json
import random
import asyncio
from datetime import date
from playwright.async_api import async_playwright

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
STORAGE_FILE = os.path.join(DATA_DIR, "threads_storage.json")
REPLY_COUNT_FILE = os.path.join(DATA_DIR, "threads_reply_count.json")

THREADS_URL = "https://www.threads.net"
DAILY_LIMIT = 10
DELAY_MIN = 30
DELAY_MAX = 90


def _load_reply_count():
    """오늘 답글 수 로드"""
    today = date.today().isoformat()
    if not os.path.exists(REPLY_COUNT_FILE):
        return today, 0
    with open(REPLY_COUNT_FILE, "r") as f:
        data = json.load(f)
    count = data.get(today, 0)
    return today, count


def _save_reply_count(today, count):
    """오늘 답글 수 저장"""
    data = {}
    if os.path.exists(REPLY_COUNT_FILE):
        with open(REPLY_COUNT_FILE, "r") as f:
            data = json.load(f)
    data[today] = count
    with open(REPLY_COUNT_FILE, "w") as f:
        json.dump(data, f, indent=2)


async def _launch_browser(pw):
    """Playwright 브라우저 + 세션 로드"""
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
    return browser, context, page


async def fetch_home_feed(max_posts=10):
    """
    Threads 홈피드에서 게시물 목록 추출

    Returns:
        list[dict]: [{"author": "@username", "text": "...", "likes": 0, "post_element_index": 0}, ...]
    """
    async with async_playwright() as pw:
        browser, context, page = await _launch_browser(pw)
        try:
            await page.goto(THREADS_URL, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 피드 게시물 컨테이너 찾기
            # Threads는 각 게시물이 article 또는 div[data-pressable-container] 안에 있음
            post_containers = await page.query_selector_all(
                'div[data-pressable-container="true"]'
            )

            if not post_containers:
                # fallback: article 태그
                post_containers = await page.query_selector_all("article")

            posts = []
            for i, container in enumerate(post_containers[:max_posts]):
                try:
                    # 작성자 추출: 프로필 링크에서 username
                    author = ""
                    author_links = await container.query_selector_all('a[href^="/@"]')
                    if author_links:
                        href = await author_links[0].get_attribute("href")
                        author = href.replace("/", "") if href else ""

                    # 게시물 텍스트 추출
                    text = ""
                    # Threads 게시물 텍스트는 보통 span 안에 있음
                    text_spans = await container.query_selector_all(
                        'div[dir="auto"] > span'
                    )
                    if text_spans:
                        parts = []
                        for span in text_spans:
                            t = await span.inner_text()
                            if t.strip():
                                parts.append(t.strip())
                        text = " ".join(parts)

                    if not text:
                        # fallback: 컨테이너 전체 텍스트에서 추출
                        full_text = await container.inner_text()
                        lines = [
                            l.strip()
                            for l in full_text.split("\n")
                            if l.strip()
                            and l.strip() not in ("좋아요", "답글", "공유", "더 보기")
                        ]
                        text = " ".join(lines[:3]) if lines else ""

                    # 좋아요 수 추출 (있으면)
                    likes = 0
                    like_el = await container.query_selector(
                        '[aria-label*="좋아요"]'
                    )
                    if like_el:
                        label = await like_el.get_attribute("aria-label")
                        if label:
                            import re

                            nums = re.findall(r"\d+", label)
                            if nums:
                                likes = int(nums[0])

                    posts.append(
                        {
                            "author": author,
                            "text": text[:200],
                            "likes": likes,
                            "post_element_index": i,
                        }
                    )
                except Exception as e:
                    print(f"[THREADS] 게시물 {i} 파싱 실패: {e}")
                    continue

            # 세션 저장 (쿠키 갱신)
            storage = await context.storage_state()
            with open(STORAGE_FILE, "w") as f:
                json.dump(storage, f)

            print(f"[THREADS] 홈피드에서 {len(posts)}개 게시물 추출")
            return posts

        finally:
            await browser.close()


async def reply_to_user(username, reply_text, post_index=0, expected_text=None):
    """
    특정 사용자의 프로필 페이지에서 게시물에 답글 달기

    Args:
        username: 대상 사용자 이름 (@ 없이)
        reply_text: 답글 텍스트
        post_index: 프로필 내 게시물 인덱스 (기본값 0 = 최신 게시물)
        expected_text: 홈피드에서 본 원본 텍스트 (있으면 프로필 게시물과 대조 검증)

    Returns:
        dict: {"success": bool, "error": str|None, "actual_text": str|None}
    """
    # 일일 제한 확인
    today, count = _load_reply_count()
    if count >= DAILY_LIMIT:
        return {"success": False, "error": f"일일 답글 제한 도달 ({DAILY_LIMIT}개)", "actual_text": None}

    async with async_playwright() as pw:
        browser, context, page = await _launch_browser(pw)
        try:
            # 프로필 페이지로 이동
            profile_url = f"{THREADS_URL}/@{username}"
            await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)

            # 게시물 컨테이너 찾기
            post_containers = await page.query_selector_all(
                'div[data-pressable-container="true"]'
            )

            if not post_containers:
                return {
                    "success": False,
                    "error": f"@{username} 프로필에서 게시물을 찾을 수 없음",
                    "actual_text": None,
                }

            # expected_text가 있으면 프로필 게시물 중 매칭되는 글을 자동 검색
            import re
            target = None
            actual_text = ""

            if expected_text:
                expected_norm = re.sub(r'\s+', '', expected_text.strip()[:30].lower())
                for idx, container in enumerate(post_containers[:10]):
                    # 각 게시물 텍스트 추출
                    candidate_text = ""
                    text_spans = await container.query_selector_all('div[dir="auto"] > span')
                    if text_spans:
                        parts = []
                        for span in text_spans:
                            t = await span.inner_text()
                            if t.strip():
                                parts.append(t.strip())
                        candidate_text = " ".join(parts)
                    if not candidate_text:
                        candidate_text = (await container.inner_text()).strip()

                    # 전체 텍스트에서 expected_text 키워드 검색 (유저네임/시간 prefix 무시)
                    candidate_norm = re.sub(r'\s+', '', candidate_text.strip().lower())
                    if expected_norm and candidate_norm and expected_norm[:15] in candidate_norm:
                        target = container
                        actual_text = candidate_text
                        print(f"[THREADS] 프로필 게시물 {idx}번에서 매칭 발견: '{candidate_text[:50]}'")
                        break

                if target is None:
                    print(f"[THREADS] @{username} 프로필에서 매칭 글 못 찾음. 예상: '{expected_text[:50]}'")
                    return {
                        "success": False,
                        "error": f"프로필에서 해당 글을 찾을 수 없음. 예상: '{expected_text[:40]}'",
                        "actual_text": None,
                    }
            else:
                # expected_text 없으면 기존 방식 (post_index 사용)
                if post_index >= len(post_containers):
                    return {
                        "success": False,
                        "error": f"게시물 인덱스 {post_index}가 범위 초과 (총 {len(post_containers)}개)",
                        "actual_text": None,
                    }
                target = post_containers[post_index]
                text_spans = await target.query_selector_all('div[dir="auto"] > span')
                if text_spans:
                    parts = []
                    for span in text_spans:
                        t = await span.inner_text()
                        if t.strip():
                            parts.append(t.strip())
                    actual_text = " ".join(parts)
                if not actual_text:
                    actual_text = (await target.inner_text()).strip()

            # 게시물 컨테이너 안에서 답글 아이콘 찾기
            # (프로필 상단 탭의 "답글"과 겹치므로 반드시 컨테이너 안에서 찾아야 함)
            reply_icon = await target.query_selector('[aria-label="답글"]')
            if not reply_icon:
                # 영어 UI fallback
                reply_icon = await target.query_selector('[aria-label="Reply"]')
            if not reply_icon:
                return {
                    "success": False,
                    "error": f"@{username} 게시물 {post_index}에서 답글 아이콘을 찾을 수 없음",
                    "actual_text": actual_text[:200] if actual_text else None,
                }

            # 답글 아이콘 클릭 -> 모달 오픈
            await reply_icon.click()
            await page.wait_for_timeout(2000)

            # 답글 입력란 찾기 (모달 내 contenteditable)
            reply_input = page.locator('[contenteditable="true"]')
            await reply_input.first.wait_for(timeout=5000)
            await reply_input.first.click()
            await page.wait_for_timeout(500)

            # 텍스트 입력 (fill 대신 keyboard.type 사용)
            await page.keyboard.type(reply_text, delay=30)
            await page.wait_for_timeout(500)

            # 게시 버튼 클릭 (exact=True로 "게시물이 페디버스에..." 등과 구분)
            post_button = page.get_by_role("button", name="게시", exact=True)
            if not await post_button.is_visible():
                # 영어 UI fallback
                post_button = page.get_by_role("button", name="Post", exact=True)
            await post_button.click()
            await page.wait_for_timeout(3000)

            # 답글 수 갱신
            _save_reply_count(today, count + 1)

            # 세션 저장
            storage = await context.storage_state()
            with open(STORAGE_FILE, "w") as f:
                json.dump(storage, f)

            print(f"[THREADS] @{username} 게시물 {post_index}에 답글 완료 (오늘 {count + 1}/{DAILY_LIMIT}개)")
            return {"success": True, "error": None, "actual_text": actual_text[:200] if actual_text else None}

        except Exception as e:
            print(f"[THREADS] 답글 실패 (@{username}): {e}")
            return {"success": False, "error": str(e), "actual_text": None}
        finally:
            await browser.close()


STOP_KEYWORDS = ["멈춰", "스톱", "stop", "중지", "그만"]


def _check_stop_signal():
    """
    poll_new_messages()로 새 메시지를 확인하고,
    멈춤 키워드가 포함되어 있으면 True 반환.
    """
    try:
        from telegram_bot import poll_new_messages
        new_msgs = poll_new_messages()
        for msg in new_msgs:
            text = msg.get("text", "").strip().lower()
            for keyword in STOP_KEYWORDS:
                if keyword in text:
                    print(f"[THREADS] 멈춤 신호 감지! 메시지: '{msg.get('text', '')}'")
                    return True
    except Exception as e:
        print(f"[THREADS] 멈춤 신호 확인 중 오류 (무시): {e}")
    return False


async def safe_reply_batch(replies):
    """
    여러 사용자 게시물에 순차적으로 답글 달기 (안전 장치 포함)

    안전 장치:
    1. expected_text로 게시물 텍스트 검증 (잘못된 글에 답글 방지)
    2. 매 답글 후 새 메시지 확인 → "멈춰" 키워드 감지 시 즉시 중단

    Args:
        replies: [{"username": "xxx", "reply_text": "...", "post_index": 0, "expected_text": "..."}, ...]

    Returns:
        list[dict]: 각 답글의 결과
    """
    today, count = _load_reply_count()
    remaining = DAILY_LIMIT - count

    if remaining <= 0:
        print(f"[THREADS] 일일 답글 제한 도달 ({DAILY_LIMIT}개)")
        return [{"success": False, "error": "일일 제한 도달"}] * len(replies)

    # 제한 초과분 잘라내기
    if len(replies) > remaining:
        print(f"[THREADS] 남은 답글 가능 수: {remaining}개, {len(replies)}개 중 {remaining}개만 처리")
        replies = replies[:remaining]

    results = []
    for i, r in enumerate(replies):
        # 답글 전 멈춤 신호 확인
        if _check_stop_signal():
            print(f"[THREADS] 사용자 요청으로 배치 중단! ({i}/{len(replies)} 완료)")
            for _ in range(len(replies) - i):
                results.append({"success": False, "error": "사용자 요청으로 중단됨"})
            break

        username = r["username"]
        reply_text = r["reply_text"]
        post_index = r.get("post_index", 0)
        expected_text = r.get("expected_text", None)
        print(f"[THREADS] 답글 {i + 1}/{len(replies)} 처리 중... (@{username})")
        result = await reply_to_user(username, reply_text, post_index, expected_text=expected_text)
        results.append(result)

        if not result["success"]:
            error_msg = result.get("error", "")
            # 텍스트 불일치/글 못 찾음은 스킵 (배치 계속)
            if "불일치" in error_msg or "찾을 수 없음" in error_msg:
                print(f"[THREADS] 스킵: {error_msg}")
                continue
            # 그 외 에러는 배치 중단
            print(f"[THREADS] 에러 발생, 배치 중단: {error_msg}")
            for _ in range(len(replies) - i - 1):
                results.append({"success": False, "error": "이전 에러로 중단됨"})
            break

        # 마지막이 아니면 랜덤 딜레이
        if i < len(replies) - 1:
            delay = random.randint(DELAY_MIN, DELAY_MAX)
            print(f"[THREADS] {delay}초 대기...")
            await asyncio.sleep(delay)

    return results


if __name__ == "__main__":

    async def main():
        print("=== Threads 홈피드 읽기 테스트 ===")
        posts = await fetch_home_feed(max_posts=5)
        for i, p in enumerate(posts):
            print(f"\n[{i}] {p['author']}")
            print(f"    {p['text'][:80]}")
            print(f"    좋아요: {p['likes']}")

        # 답글 테스트 (주석 해제해서 사용)
        # result = await reply_to_user("target_username", "답글 테스트!", post_index=0)
        # print(f"\n답글 결과: {result}")

    asyncio.run(main())
