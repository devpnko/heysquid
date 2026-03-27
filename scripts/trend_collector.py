"""
트렌드 수집기 — signal.bz + 이지텍스트 API
매일 수집해서 data/trends_log.json에 쌓아둠.
SQUID가 "사주/MBTI로 풀 수 있는 소재" 판단할 때 참고.

사용법:
  python3 scripts/trend_collector.py              # 수집 + 저장
  python3 scripts/trend_collector.py --show       # 오늘 트렌드 보기
"""

import argparse
import json
import os
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
TRENDS_LOG = os.path.join(PROJECT_ROOT, "data", "trends_log.json")


def collect_signal_bz() -> list[dict]:
    """signal.bz 네이버 실시간 검색어 수집."""
    try:
        from playwright.sync_api import sync_playwright

        p = sync_playwright().start()
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://www.signal.bz/", timeout=30000)

        import time
        time.sleep(5)

        items = page.evaluate("""() => {
            const results = [];
            document.querySelectorAll('.rank-layer').forEach(el => {
                const num = el.querySelector('.rank-num')?.innerText?.trim() || '';
                const text = el.querySelector('.rank-text')?.innerText?.trim() || '';
                if (num && text) {
                    results.push({rank: parseInt(num), keyword: text});
                }
            });
            return results;
        }""")

        browser.close()
        p.stop()
        return items

    except Exception as e:
        print(f"signal.bz 수집 실패: {e}")
        return []


def collect_easytext_google() -> list[dict]:
    """이지텍스트 API — 구글 실시간 트렌드."""
    try:
        import requests
        resp = requests.get(
            "https://easytext.store/api/trends",
            headers={"Referer": "https://easytext.store/"},
            timeout=15,
        )
        if resp.ok:
            return resp.json().get("items", [])
    except Exception as e:
        print(f"구글 트렌드 수집 실패: {e}")
    return []


def collect_easytext_threads() -> list[dict]:
    """이지텍스트 API — 스레드 떡상 키워드."""
    try:
        import requests
        resp = requests.get(
            "https://easytext.store/api/threads/trends",
            headers={"Referer": "https://easytext.store/"},
            timeout=15,
        )
        if resp.ok:
            return resp.json().get("trends", [])
    except Exception as e:
        print(f"스레드 트렌드 수집 실패: {e}")
    return []


def collect_all() -> dict:
    """전체 트렌드 수집."""
    now = datetime.now()

    print("📡 signal.bz 수집 중...", flush=True)
    signal = collect_signal_bz()
    print(f"  → {len(signal)}개", flush=True)

    print("📡 구글 트렌드 수집 중...", flush=True)
    google = collect_easytext_google()
    print(f"  → {len(google)}개", flush=True)

    print("📡 스레드 떡상 키워드 수집 중...", flush=True)
    threads = collect_easytext_threads()
    print(f"  → {len(threads)}개", flush=True)

    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "signal_bz": signal,
        "google_trends": google,
        "threads_trends": threads,
    }


def save_trends(entry: dict):
    """트렌드 로그에 추가."""
    if os.path.exists(TRENDS_LOG):
        with open(TRENDS_LOG, encoding="utf-8") as f:
            log = json.load(f)
    else:
        log = {"entries": []}

    # 오늘 같은 시간대 중복 방지 (같은 날 같은 시간이면 덮어쓰기)
    log["entries"] = [
        e for e in log["entries"]
        if not (e["date"] == entry["date"] and e["time"] == entry["time"])
    ]
    log["entries"].append(entry)

    # 최근 30일만 유지
    log["entries"] = log["entries"][-90:]

    with open(TRENDS_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def show_today():
    """오늘 수집된 트렌드 보기."""
    if not os.path.exists(TRENDS_LOG):
        print("수집된 트렌드 없음")
        return

    with open(TRENDS_LOG, encoding="utf-8") as f:
        log = json.load(f)

    today = datetime.now().strftime("%Y-%m-%d")
    todays = [e for e in log["entries"] if e["date"] == today]

    if not todays:
        print(f"{today} 트렌드 없음")
        return

    latest = todays[-1]
    print(f"📊 {latest['date']} {latest['time']} 트렌드\n")

    print("=== 네이버 실시간 (signal.bz) ===")
    for s in latest.get("signal_bz", []):
        print(f"  {s['rank']}. {s['keyword']}")

    print("\n=== 구글 트렌드 ===")
    for g in latest.get("google_trends", []):
        print(f"  {g['rank']}. {g['keyword']} ({g.get('traffic','')})")

    print("\n=== 스레드 떡상 키워드 ===")
    for t in latest.get("threads_trends", []):
        print(f"  {t['rank']}. {t['keyword']} [{t.get('category','')}] (↑{t.get('risingIndex','')})")


def main():
    parser = argparse.ArgumentParser(description="트렌드 수집기")
    parser.add_argument("--show", action="store_true", help="오늘 트렌드 보기")
    args = parser.parse_args()

    if args.show:
        show_today()
        return

    entry = collect_all()
    save_trends(entry)

    print(f"\n✅ 저장 완료 → {TRENDS_LOG}")
    print(f"   signal.bz: {len(entry['signal_bz'])}개")
    print(f"   구글: {len(entry['google_trends'])}개")
    print(f"   스레드: {len(entry['threads_trends'])}개")

    # 간단히 출력
    print("\n📊 네이버 TOP 5:")
    for s in entry["signal_bz"][:5]:
        print(f"  {s['rank']}. {s['keyword']}")


if __name__ == "__main__":
    main()
