"""heysquid CLI — init / start / stop / restart / status / logs / tui."""

import argparse
import os
import shutil
import sys

from .. import __version__
from .config import (
    PROJECT_ROOT, DATA_DIR, TASKS_DIR, WORKSPACES_DIR, LOGS_DIR,
    PACKAGE_DIR, get_env_path, get_template_path,
)


def cmd_init(args):
    """Initialize a heysquid environment with interactive setup."""
    target = args.dir or str(PROJECT_ROOT)
    data_dir = os.path.join(target, "data")

    print("heysquid init")
    print("=" * 40)
    print()

    # Step 1: 환경 확인
    print("[1/5] 환경 확인...")
    py_version = sys.version.split()[0]
    print(f"  Python: {py_version}")
    if sys.version_info < (3, 10):
        print("  [ERROR] Python 3.10 이상이 필요합니다.")
        sys.exit(1)

    claude_found = shutil.which("claude")
    if claude_found:
        print(f"  Claude CLI: {claude_found}")
    else:
        print("  [WARN] Claude CLI가 설치되지 않았습니다.")
        print("         https://docs.anthropic.com/en/docs/claude-code 에서 설치하세요.")
    print()

    # 디렉토리 생성
    print(f"[2/5] 디렉토리 생성 ({target})...")
    for d in [data_dir, os.path.join(target, "tasks"),
              os.path.join(target, "workspaces"), os.path.join(target, "logs")]:
        os.makedirs(d, exist_ok=True)
        print(f"  {os.path.basename(d)}/")

    # 템플릿 복사
    templates = {
        "env.example": os.path.join(data_dir, ".env"),
        "identity.json": os.path.join(data_dir, "identity.json"),
        "team_playbook.md": os.path.join(data_dir, "team_playbook.md"),
    }

    for tmpl_name, dest in templates.items():
        if not os.path.exists(dest):
            src = get_template_path(tmpl_name)
            if os.path.exists(src):
                shutil.copy2(src, dest)
                print(f"  Created {os.path.basename(dest)}")
        else:
            print(f"  Exists  {os.path.basename(dest)}")
    print()

    # Step 3: 텔레그램 봇 토큰
    env_file = os.path.join(data_dir, ".env")
    # dev mode: heysquid/.env 위치도 체크
    dev_env = os.path.join(str(PACKAGE_DIR), ".env")
    existing_env = dev_env if os.path.exists(dev_env) else env_file

    if os.path.exists(existing_env) and _env_has_token(existing_env):
        print("[3/5] 텔레그램 봇 토큰: 이미 설정됨")
    else:
        print("[3/5] 텔레그램 봇 토큰 설정")
        print("  BotFather(@BotFather)에서 봇을 만들고 토큰을 받으세요.")
        token = input("  봇 토큰 입력 (건너뛰려면 Enter): ").strip()
        if token:
            _write_env_token(env_file, "TELEGRAM_BOT_TOKEN", token)
            print("  [OK] 토큰 저장됨")
        else:
            print("  [SKIP] 나중에 .env 파일을 직접 수정하세요.")
    print()

    # Step 4: 사용자 ID
    print("[4/5] 텔레그램 사용자 ID")
    print("  봇에게 메시지를 보낸 후, @userinfobot으로 ID를 확인하세요.")
    user_id = input("  사용자 ID 입력 (건너뛰려면 Enter): ").strip()
    if user_id:
        _write_env_token(env_file, "TELEGRAM_ALLOWED_USERS", user_id)
        print("  [OK] 사용자 ID 저장됨")
    else:
        print("  [SKIP] 나중에 .env 파일을 직접 수정하세요.")
    print()

    # Step 5: 자동 시작
    print("[5/5] 설정 완료!")
    print()
    print("다음 단계:")
    print(f"  1. .env 파일 확인: {env_file}")
    print("  2. 데몬 시작: heysquid start")
    print("  3. 상태 확인: heysquid status")


def _env_has_token(env_path: str) -> bool:
    """Check if .env has a real bot token (not placeholder)."""
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    val = line.split("=", 1)[1].strip()
                    return val and val != "your_bot_token_here"
    except Exception:
        pass
    return False


def _write_env_token(env_path: str, key: str, value: str) -> None:
    """Write or update a key=value in .env file."""
    lines = []
    found = False
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break

    if not found:
        lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)


def cmd_start(args):
    """Start the heysquid daemon."""
    from .daemon import start
    print("heysquid 데몬 시작...\n")
    start()


def cmd_stop(args):
    """Stop the heysquid daemon."""
    from .daemon import stop
    print("heysquid 데몬 중지...\n")
    stop()


def cmd_restart(args):
    """Restart the heysquid daemon."""
    from .daemon import restart
    restart()


def cmd_status(args):
    """Show daemon status."""
    from .daemon import status
    status()


def cmd_logs(args):
    """Show recent logs."""
    from .daemon import logs
    logs(follow=args.follow)


def cmd_tui(args):
    """Launch TUI monitor."""
    tui_app = os.path.join(str(PROJECT_ROOT), "scripts", "tui_textual", "app.py")
    if os.path.exists(tui_app):
        python = sys.executable
        os.execvp(python, [python, tui_app])
    else:
        # Try as module
        try:
            from scripts.tui_textual.app import SquidApp
            app = SquidApp()
            app.run()
        except ImportError:
            print("[ERROR] TUI 앱을 찾을 수 없습니다.")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        prog="heysquid",
        description="Your personal PM agent",
    )
    parser.add_argument("--version", action="version",
                        version=f"heysquid {__version__}")

    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize heysquid environment")
    p_init.add_argument("--dir", help="Target directory (default: auto-detected)")

    sub.add_parser("start", help="Start daemon")
    sub.add_parser("stop", help="Stop daemon")
    sub.add_parser("restart", help="Restart daemon")
    sub.add_parser("status", help="Show status")

    p_logs = sub.add_parser("logs", help="Show recent logs")
    p_logs.add_argument("-f", "--follow", action="store_true",
                        help="Follow log output (tail -f)")

    sub.add_parser("tui", help="Launch TUI monitor")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
        "logs": cmd_logs,
        "tui": cmd_tui,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
