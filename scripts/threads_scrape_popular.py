"""
Threads homefeed + reference account popular posts scraping script.
- Uses Playwright headful Chromium
- Session: data/threads_storage.json
- Output: /tmp/threads_popular_posts.json
"""

import json
import os
import re
import time
import sys

from playwright.sync_api import sync_playwright

from heysquid.core.config import DATA_DIR_STR

STORAGE_PATH = os.path.join(DATA_DIR_STR, "threads_storage.json")
OUTPUT_PATH = "/tmp/threads_popular_posts.json"

REFERENCE_ACCOUNTS = [
    "choi.openai",
    "smart_daddy_ai",
    "since_1985_love",
    "leosofts2016",
]


def extract_username_from_container(container) -> str:
    """Extract author username from container."""
    # Extract from /@username pattern links (those without post/ are profile links)
    links = container.query_selector_all("a[href]")
    for link in links:
        href = link.get_attribute("href") or ""
        # /@username format (exclude post/, media, replies, etc.)
        m = re.match(r"^/@([^/]+)$", href)
        if m:
            return "@" + m.group(1)
    return ""


def extract_text_from_container(container) -> str:
    """Extract body text from container."""
    full_text = container.inner_text()
    lines = full_text.split("\n")

    # Time patterns: "N분(min)", "N시간(hr)", "N일(day)", "N주(week)", "방금(just now)", "YYYY-MM-DD"
    time_pattern = re.compile(
        r"^(\d+[분시일주]|방금|\d+[mhd]w?|just now|\d{4}-\d{2}-\d{2})$",
        re.IGNORECASE,
    )
    # Lines with only numbers (like count, reply count, etc.) -- including "/" slide indicators
    num_pattern = re.compile(r"^[\d,./]+$")
    # Repost notification lines (Korean: "님이 ... 리포스트함")
    repost_pattern = re.compile(r"님이 .+ 리포스트함")
    # Follow/Following (Korean UI text)
    follow_pattern = re.compile(r"^(팔로우|팔로잉)$")
    # Pinned indicator (Korean: "고정됨")
    pinned_pattern = re.compile(r"^고정됨$")
    # URL lines (domain patterns)
    url_pattern = re.compile(r"^https?://|\.com|\.kr|\.net|\.io")
    # Hashtag-only lines (just words or hashtag link text)
    # e.g., "AI Threads", "Vibe coding"
    # These lines appear just before the time pattern as tag labels, so skip them
    # If they appear after the time, treat them as body text

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
            # Skip pre-time content: username, hashtag labels, dates
            continue

        if state == "collecting":
            if num_pattern.match(stripped):
                # Numbers-only line means end of body
                break
            # Skip URL or domain lines
            if url_pattern.search(stripped) and len(stripped) < 60:
                continue
            content_lines.append(stripped)

    text = "\n".join(content_lines).strip()
    return text


def extract_counts_from_container(container) -> tuple[str, str]:
    """Extract like count and reply count from container.

    Threads homefeed structure:
    - Like/reply counts are displayed as number-only spans (no aria-label)
    - Trailing numbers in the container's full text represent likes/replies
    """
    full_text = container.inner_text()
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    # Collect number-only lines from the end
    num_pattern = re.compile(r"^[\d,]+$")
    trailing_nums = []
    for line in reversed(lines):
        if num_pattern.match(line):
            trailing_nums.insert(0, line.replace(",", ""))
        else:
            break

    # Exclude slide indicators (e.g. 1/5)
    slash_pattern = re.compile(r"^\d+/\d+$")
    trailing_nums = [n for n in trailing_nums if not slash_pattern.match(n)]

    # Threads: order is typically [likes, replies, reposts, quotes] or [replies, likes]
    # The actual order of trailing numbers may vary
    # Empirically: first = likes, second = replies (or vice versa)
    # Safer approach: try aria-label buttons first

    # Try aria-label from buttons
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

    # Fall back to trailing_nums if aria-label didn't work
    if likes == "0" and trailing_nums:
        likes = trailing_nums[0] if trailing_nums else "0"
    if replies == "0" and len(trailing_nums) > 1:
        replies = trailing_nums[1]

    return likes, replies


def scroll_and_collect(page, source: str, target_count: int = 20) -> list[dict]:
    """Scroll page and collect up to target_count posts."""
    posts = []
    seen_texts = set()
    max_scrolls = 40
    scroll_count = 0
    prev_count = 0
    stale_count = 0

    print(f"[{source}] Starting collection (target: {target_count})...", flush=True)

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

                # Deduplication (username + first 40 chars of text)
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

        # Increment staleness count if no new posts were added
        if len(posts) == prev_count:
            stale_count += 1
        else:
            stale_count = 0
        prev_count = len(posts)

        # After 3 consecutive stale rounds, try more aggressive scrolling
        if stale_count >= 3 and scroll_count < max_scrolls - 5:
            # Scroll to page bottom and wait
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(3)
            stale_count = 0
        else:
            page.evaluate("window.scrollBy(0, 800)")
            time.sleep(2)

        scroll_count += 1

    print(f"[{source}] Collection complete: {len(posts)} posts ({scroll_count} scrolls)", flush=True)
    return posts


def scrape_homefeed(page) -> list[dict]:
    """Scrape threads.com homefeed."""
    print("\n[homefeed] Connecting to threads.com...", flush=True)
    page.goto("https://www.threads.com/", timeout=30000)

    # Wait for login verification
    try:
        page.wait_for_selector("div[data-pressable-container]", timeout=15000)
    except Exception:
        print("[homefeed] Failed to load posts -- login required or page error", flush=True)
        # Check current URL
        print(f"  Current URL: {page.url}", flush=True)
        return []

    time.sleep(2)
    return scroll_and_collect(page, "homefeed", target_count=20)


def scrape_profile(page, username: str) -> list[dict]:
    """Scrape a specific account's profile page."""
    url = f"https://www.threads.com/@{username}"
    print(f"\n[profile] Connecting to @{username}...", flush=True)

    try:
        page.goto(url, timeout=30000)
    except Exception as e:
        print(f"[profile] Page navigation failed: {e}", flush=True)
        return []

    # Wait for profile page to load
    try:
        page.wait_for_selector("div[data-pressable-container]", timeout=15000)
    except Exception:
        # 404 or private account
        title = page.title()
        print(f"[profile] @{username} -- No posts (title={title!r})", flush=True)
        return []

    time.sleep(2)
    posts = scroll_and_collect(page, f"profile:{username}", target_count=5)
    return posts


def main():
    all_posts = []

    with sync_playwright() as p:
        print("Starting Playwright Chromium (headful)...", flush=True)
        browser = p.chromium.launch(
            headless=False,
            args=["--window-size=1280,900", "--disable-blink-features=AutomationControlled"],
        )

        # Create context with saved session
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
            print("Saved session loaded.", flush=True)
        except Exception as e:
            print(f"Session load failed: {e} -- creating new context", flush=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})

        page = context.new_page()

        # 1. Scrape homefeed
        homefeed_posts = scrape_homefeed(page)
        all_posts.extend(homefeed_posts)

        # 2. Scrape reference accounts
        for account in REFERENCE_ACCOUNTS:
            profile_posts = scrape_profile(page, account)
            all_posts.extend(profile_posts)
            time.sleep(2)

        # Save session (refresh)
        try:
            updated_storage = context.storage_state()
            with open(STORAGE_PATH, "w") as f:
                json.dump(updated_storage, f, ensure_ascii=False, indent=2)
            print("\nSession saved.", flush=True)
        except Exception as e:
            print(f"Session save failed: {e}", flush=True)

        browser.close()

    # Save results
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_posts, f, ensure_ascii=False, indent=2)

    print(f"\nTotal {len(all_posts)} posts collected -> {OUTPUT_PATH}", flush=True)
    print_results(all_posts)
    return all_posts


def print_results(posts: list[dict]):
    print("\n" + "=" * 70, flush=True)
    print(f"Collected posts ({len(posts)} total)", flush=True)
    print("=" * 70, flush=True)

    for i, post in enumerate(posts, 1):
        src_label = {
            "homefeed": "homefeed",
        }.get(post["source"], post["source"].replace("profile:", "@"))
        print(f"\n[{i}] {post['username']}  ({src_label})", flush=True)
        print(f"    Likes {post['likes']}  |  Replies {post['replies']}", flush=True)
        print(f"    {post['text'][:300]}", flush=True)
        print("    " + "-" * 50, flush=True)


if __name__ == "__main__":
    main()
