"""
범용 브라우저 로그인 — Playwright persistent context로 세션 저장

사용법:
  python3 scripts/browser_login.py threads ambition_monkey
  python3 scripts/browser_login.py x
  python3 scripts/browser_login.py reddit
  python3 scripts/browser_login.py linkedin
  python3 scripts/browser_login.py --list
"""

import argparse
import os
import sys

from playwright.sync_api import sync_playwright

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLATFORMS = {
    "threads": {
        "url": "https://www.threads.net/login",
        "accounts": {
            "dkbsqd.official": "threads_browser_data",
            "ambition_monkey": "threads_browser_data_ambition",
            "default": "threads_browser_data",
        },
    },
    "x": {
        "url": "https://x.com/i/flow/login",
        "accounts": {"default": "browser_x"},
    },
    "reddit": {
        "url": "https://www.reddit.com/login/",
        "accounts": {"default": "browser_reddit"},
    },
    "linkedin": {
        "url": "https://www.linkedin.com/login",
        "accounts": {"default": "browser_linkedin"},
    },
}


def get_browser_data(platform: str, account: str = "default") -> str:
    cfg = PLATFORMS[platform]["accounts"]
    dirname = cfg.get(account, cfg["default"])
    return os.path.join(PROJECT_ROOT, "data", dirname)


def clean_locks(browser_data: str):
    for name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        path = os.path.join(browser_data, name)
        if os.path.exists(path):
            os.remove(path)


def do_login(platform: str, account: str = "default"):
    cfg = PLATFORMS[platform]
    bd = get_browser_data(platform, account)
    os.makedirs(bd, exist_ok=True)
    clean_locks(bd)

    label = f"{platform}" + (f" ({account})" if account != "default" else "")
    print(f"\n{'='*50}", flush=True)
    print(f"  {label}", flush=True)
    print(f"  세션: {bd}", flush=True)
    print(f"  URL: {cfg['url']}", flush=True)
    print(f"{'='*50}\n", flush=True)

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            bd,
            channel="chrome",
            headless=False,
            viewport=None,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
            ignore_default_args=["--enable-automation"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(cfg["url"], timeout=30000)
        print("브라우저에서 로그인해주세요.", flush=True)
        print("로그인 완료 후 Enter를 누르세요...", flush=True)
        input()
        context.close()

    print(f"[{label}] 세션 저장 완료!\n", flush=True)


def main():
    parser = argparse.ArgumentParser(description="범용 브라우저 로그인")
    parser.add_argument("platform", nargs="?", choices=list(PLATFORMS.keys()),
                        help="플랫폼 (threads, x, reddit, linkedin)")
    parser.add_argument("account", nargs="?", default="default",
                        help="계정 (threads: dkbsqd.official, ambition_monkey)")
    parser.add_argument("--list", action="store_true", help="지원 플랫폼 목록")
    parser.add_argument("--all", action="store_true",
                        help="모든 플랫폼 순차 로그인")
    args = parser.parse_args()

    if args.list:
        for name, cfg in PLATFORMS.items():
            accounts = ", ".join(cfg["accounts"].keys())
            print(f"  {name:12s} → {cfg['url']:40s} [{accounts}]")
        return

    if args.all:
        # threads ambition → x → reddit → linkedin
        do_login("threads", "ambition_monkey")
        do_login("x")
        do_login("reddit")
        do_login("linkedin")
        print("\n모든 플랫폼 로그인 완료!", flush=True)
        return

    if not args.platform:
        parser.error("플랫폼을 선택하세요 (또는 --all / --list)")

    do_login(args.platform, args.account)


if __name__ == "__main__":
    main()
