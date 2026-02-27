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

    # Step 1: Check environment
    print("[1/5] Checking environment...")
    py_version = sys.version.split()[0]
    print(f"  Python: {py_version}")
    if sys.version_info < (3, 10):
        print("  [ERROR] Python 3.10 or higher is required.")
        sys.exit(1)

    claude_found = shutil.which("claude")
    if claude_found:
        print(f"  Claude CLI: {claude_found}")
    else:
        print("  [WARN] Claude CLI is not installed.")
        print("         Install from https://docs.anthropic.com/en/docs/claude-code")
    print()

    # Create directories
    print(f"[2/5] Creating directories ({target})...")
    for d in [data_dir, os.path.join(target, "tasks"),
              os.path.join(target, "workspaces"), os.path.join(target, "logs")]:
        os.makedirs(d, exist_ok=True)
        print(f"  {os.path.basename(d)}/")

    # Copy templates
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

    # Step 3: Telegram bot token
    env_file = os.path.join(data_dir, ".env")
    # dev mode: also check heysquid/.env location
    dev_env = os.path.join(str(PACKAGE_DIR), ".env")
    existing_env = dev_env if os.path.exists(dev_env) else env_file

    if os.path.exists(existing_env) and _env_has_token(existing_env, "TELEGRAM_BOT_TOKEN"):
        print("[3/7] Telegram bot token: already configured")
    else:
        print("[3/7] Telegram bot token")
        print("  Create a bot via @BotFather on Telegram and paste the token.")
        token = input("  Bot token (Enter to skip): ").strip()
        if token:
            _write_env_token(env_file, "TELEGRAM_BOT_TOKEN", token)
            print("  [OK] Saved")
        else:
            print("  [SKIP] Edit .env later.")
    print()

    # Step 4: Telegram user ID
    print("[4/7] Telegram user ID")
    print("  Send a message to @userinfobot on Telegram to get your ID.")
    user_id = input("  User ID (Enter to skip): ").strip()
    if user_id:
        _write_env_token(env_file, "TELEGRAM_ALLOWED_USERS", user_id)
        print("  [OK] Saved")
    else:
        print("  [SKIP] Edit .env later.")
    print()

    # Step 5: Slack (optional)
    print("[5/7] Slack integration (optional)")
    if os.path.exists(existing_env) and _env_has_token(existing_env, "SLACK_BOT_TOKEN"):
        print("  Already configured.")
    else:
        print("  Connect Slack to control your PM from Slack too.")
        print("  Requires: Slack App with Socket Mode enabled")
        print("  Guide: https://api.slack.com/apps")
        slack = input("  Configure Slack? [y/N]: ").strip().lower()
        if slack in ("y", "yes"):
            bot_token = input("  Slack Bot Token (xoxb-...): ").strip()
            app_token = input("  Slack App Token (xapp-...): ").strip()
            channel = input("  Default channel ID (C...): ").strip()
            users = input("  Allowed user IDs (comma-separated, U...): ").strip()
            if bot_token:
                _write_env_token(env_file, "SLACK_BOT_TOKEN", bot_token)
            if app_token:
                _write_env_token(env_file, "SLACK_APP_TOKEN", app_token)
            if channel:
                _write_env_token(env_file, "SLACK_DEFAULT_CHANNEL", channel)
            if users:
                _write_env_token(env_file, "SLACK_ALLOWED_USERS", users)
            print("  [OK] Slack configured")
            print("  Tip: pip install 'heysquid[slack]' to install dependencies")
        else:
            print("  [SKIP] Add Slack anytime by editing .env")
    print()

    # Step 6: Discord (optional)
    print("[6/7] Discord integration (optional)")
    if os.path.exists(existing_env) and _env_has_token(existing_env, "DISCORD_BOT_TOKEN"):
        print("  Already configured.")
    else:
        print("  Connect Discord to control your PM from Discord too.")
        print("  Requires: Discord Bot with MESSAGE CONTENT INTENT enabled")
        print("  Guide: https://discord.com/developers/applications")
        discord_yn = input("  Configure Discord? [y/N]: ").strip().lower()
        if discord_yn in ("y", "yes"):
            bot_token = input("  Discord Bot Token: ").strip()
            channel = input("  Default channel ID: ").strip()
            users = input("  Allowed user IDs (comma-separated): ").strip()
            if bot_token:
                _write_env_token(env_file, "DISCORD_BOT_TOKEN", bot_token)
            if channel:
                _write_env_token(env_file, "DISCORD_DEFAULT_CHANNEL", channel)
            if users:
                _write_env_token(env_file, "DISCORD_ALLOWED_USERS", users)
            print("  [OK] Discord configured")
            print("  Tip: pip install 'heysquid[discord]' to install dependencies")
        else:
            print("  [SKIP] Add Discord anytime by editing .env")
    print()

    # Step 7: Done
    print("[7/7] Setup complete!")
    print()
    print("Next steps:")
    print(f"  1. Review .env: {env_file}")
    print("  2. Start daemon: heysquid start")
    print("  3. Check status: heysquid status")
    print()
    print("Optional:")
    print("  pip install 'heysquid[slack]'     # Add Slack support")
    print("  pip install 'heysquid[discord]'   # Add Discord support")
    print("  pip install 'heysquid[all]'       # Install everything")


def _env_has_token(env_path: str, key: str = "TELEGRAM_BOT_TOKEN") -> bool:
    """Check if .env has a real value for the given key (not placeholder)."""
    placeholders = {"your_bot_token_here", "xoxb-...", "xapp-...", ""}
    try:
        with open(env_path) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    val = line.split("=", 1)[1].strip()
                    return val not in placeholders
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
    print("Starting heysquid daemon...\n")
    start()


def cmd_stop(args):
    """Stop the heysquid daemon."""
    from .daemon import stop
    print("Stopping heysquid daemon...\n")
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
            print("[ERROR] TUI app not found.")
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
