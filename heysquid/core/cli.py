"""heysquid CLI — init / start / stop / status."""

import argparse
import os
import shutil
import sys

from .. import __version__
from .config import PROJECT_ROOT, DATA_DIR, TASKS_DIR, WORKSPACES_DIR, LOGS_DIR, get_template_path


def cmd_init(args):
    """Initialize a heysquid data directory."""
    target = args.dir or str(PROJECT_ROOT)
    data_dir = os.path.join(target, "data")

    print(f"Initializing heysquid in {target} ...")

    for d in [data_dir, os.path.join(target, "tasks"),
              os.path.join(target, "workspaces"), os.path.join(target, "logs")]:
        os.makedirs(d, exist_ok=True)

    # Copy templates
    templates = {
        "env.example": os.path.join(data_dir, ".env"),
        "identity.json": os.path.join(data_dir, "identity.json"),
        "team_playbook.md": os.path.join(data_dir, "team_playbook.md"),
        "dashboard.html": os.path.join(data_dir, "dashboard.html"),
    }

    for tmpl_name, dest in templates.items():
        if not os.path.exists(dest):
            src = get_template_path(tmpl_name)
            if os.path.exists(src):
                shutil.copy2(src, dest)
                print(f"  Created {dest}")
            else:
                print(f"  [WARN] Template not found: {tmpl_name}")
        else:
            print(f"  Exists  {dest}")

    print()
    print("Next steps:")
    print(f"  1. Edit {os.path.join(data_dir, '.env')} with your Telegram bot token")
    print("  2. Run: heysquid start")


def cmd_start(args):
    """Start the heysquid daemon (delegates to scripts/run.sh)."""
    run_sh = os.path.join(str(PROJECT_ROOT), "scripts", "run.sh")
    if os.path.exists(run_sh):
        os.execvp("bash", ["bash", run_sh, "start"])
    else:
        print("[ERROR] scripts/run.sh not found. Are you in the project directory?")
        sys.exit(1)


def cmd_stop(args):
    """Stop the heysquid daemon."""
    run_sh = os.path.join(str(PROJECT_ROOT), "scripts", "run.sh")
    if os.path.exists(run_sh):
        os.execvp("bash", ["bash", run_sh, "stop"])
    else:
        print("[ERROR] scripts/run.sh not found.")
        sys.exit(1)


def cmd_status(args):
    """Show daemon status."""
    run_sh = os.path.join(str(PROJECT_ROOT), "scripts", "run.sh")
    if os.path.exists(run_sh):
        os.execvp("bash", ["bash", run_sh, "status"])
    else:
        print("[ERROR] scripts/run.sh not found.")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(prog="heysquid", description="Your personal PM agent")
    parser.add_argument("--version", action="version", version=f"heysquid {__version__}")

    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize data directory")
    p_init.add_argument("--dir", help="Target directory (default: auto-detected)")

    sub.add_parser("start", help="Start daemon")
    sub.add_parser("stop", help="Stop daemon")
    sub.add_parser("status", help="Show status")

    args = parser.parse_args()

    commands = {
        "init": cmd_init,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
