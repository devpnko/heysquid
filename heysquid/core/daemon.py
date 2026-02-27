"""heysquid.core.daemon — launchd daemon management (macOS).

plist template rendering, launchd register/unregister, process management.
"""

import os
import shutil
import subprocess
import sys
import signal
import time
from pathlib import Path

from .config import (
    PROJECT_ROOT, DATA_DIR, LOGS_DIR, PACKAGE_DIR,
    PROJECT_ROOT_STR, get_env_path,
)

LAUNCH_AGENTS = Path.home() / "Library" / "LaunchAgents"

PLIST_NAMES = [
    "com.heysquid.watcher",
    "com.heysquid.scheduler",
    "com.heysquid.slack",
    "com.heysquid.discord",
]

# Optional services that require a token to start
OPTIONAL_SERVICES = {
    "com.heysquid.slack": "SLACK_BOT_TOKEN",
    "com.heysquid.discord": "DISCORD_BOT_TOKEN",
}


def _python_path() -> str:
    """Return the python path from the current venv."""
    venv_python = PROJECT_ROOT / "venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _template_dir() -> Path:
    """Path to plist template directory."""
    # Package templates/launchd/
    pkg_templates = PACKAGE_DIR / "templates" / "launchd"
    if pkg_templates.is_dir():
        return pkg_templates
    # Project root templates/launchd/
    root_templates = PROJECT_ROOT / "templates" / "launchd"
    if root_templates.is_dir():
        return root_templates
    raise FileNotFoundError("Could not find plist template directory.")


def render_plist(template_path: Path, output_path: Path) -> None:
    """Render plist template by replacing placeholders with actual values and save."""
    content = template_path.read_text(encoding="utf-8")
    replacements = {
        "{{PROJECT_ROOT}}": PROJECT_ROOT_STR,
        "{{PYTHON}}": _python_path(),
        "{{HOME}}": str(Path.home()),
    }
    for placeholder, value in replacements.items():
        content = content.replace(placeholder, value)
    output_path.write_text(content, encoding="utf-8")


def _load_env_tokens() -> dict:
    """Load .env to check for token existence."""
    env_path = get_env_path()
    tokens = {}
    if os.path.exists(env_path):
        from dotenv import dotenv_values
        tokens = dotenv_values(env_path)
    return tokens


def start() -> None:
    """Start daemon: render plist -> register with launchd."""
    LAUNCH_AGENTS.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tmpl_dir = _template_dir()
    env_tokens = _load_env_tokens()

    # Remove legacy briefing plist
    briefing_dst = LAUNCH_AGENTS / "com.heysquid.briefing.plist"
    if briefing_dst.exists():
        subprocess.run(["launchctl", "unload", str(briefing_dst)],
                       capture_output=True)
        briefing_dst.unlink(missing_ok=True)

    for name in PLIST_NAMES:
        # Optional service: skip if token is missing
        required_token = OPTIONAL_SERVICES.get(name)
        if required_token and not env_tokens.get(required_token):
            continue

        template = tmpl_dir / f"{name}.plist.template"
        if not template.exists():
            print(f"  [WARN] Template not found: {template.name}")
            continue

        dst = LAUNCH_AGENTS / f"{name}.plist"
        render_plist(template, dst)
        subprocess.run(["launchctl", "load", str(dst)], capture_output=True)

        label = name.split(".")[-1].upper()
        print(f"  [OK] {label} started")

    # Dashboard server
    _start_dashboard_server()

    print()
    print(f"Dashboard: http://localhost:8420/dashboard.html")
    print(f"Logs: tail -f {LOGS_DIR / 'executor.log'}")
    print(f"Check status: heysquid status")


def _start_dashboard_server() -> None:
    """Start dashboard HTTP server (skip if already running)."""
    result = subprocess.run(
        ["lsof", "-i", ":8420"],
        capture_output=True,
    )
    if result.returncode == 0:
        print("  [OK] Dashboard server already running")
        return

    serve_sh = PROJECT_ROOT / "scripts" / "serve_dashboard.sh"
    if serve_sh.exists():
        log_file = LOGS_DIR / "dashboard_server.log"
        with open(log_file, "a") as lf:
            subprocess.Popen(
                ["bash", str(serve_sh)],
                stdout=lf, stderr=lf,
                start_new_session=True,
            )
        print("  [OK] Dashboard server started")


def stop() -> None:
    """Stop daemon: unload launchd + kill processes."""
    # 1. Unload launchd
    for name in PLIST_NAMES + ["com.heysquid.briefing"]:
        dst = LAUNCH_AGENTS / f"{name}.plist"
        if dst.exists():
            subprocess.run(["launchctl", "unload", str(dst)], capture_output=True)
            dst.unlink(missing_ok=True)

    # 2. Stop dashboard server
    subprocess.run(["pkill", "-f", "http.server 8420"], capture_output=True)

    # 3. Kill executor + Claude processes
    subprocess.run(["pkill", "-f", "bash.*executor.sh"], capture_output=True)

    # caffeinate -> trace and kill parent (claude)
    _kill_claude_processes()

    # 4. Additional listener processes
    for pattern in ["slack_listener", "discord_listener"]:
        subprocess.run(["pkill", "-f", pattern], capture_output=True)

    # 5. Clean up lock/pid files
    for fname in ["executor.lock", "executor.pid", "working.json", "claude.pid"]:
        fpath = DATA_DIR / fname
        fpath.unlink(missing_ok=True)

    print("[OK] Daemon + lock files cleaned up")


def _kill_claude_processes() -> None:
    """Trace and kill Claude processes via caffeinate wrapper."""
    result = subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        subprocess.run(["pkill", "-f", "append-system-prompt-file"],
                       capture_output=True)
        return

    for cpid in result.stdout.strip().split("\n"):
        cpid = cpid.strip()
        if not cpid:
            continue
        # caffeinate's parent = claude
        parent_result = subprocess.run(
            ["ps", "-p", cpid, "-o", "ppid="],
            capture_output=True, text=True,
        )
        parent = parent_result.stdout.strip()
        if parent:
            subprocess.run(["kill", parent], capture_output=True)
        subprocess.run(["kill", cpid], capture_output=True)

    subprocess.run(["pkill", "-f", "append-system-prompt-file"],
                   capture_output=True)
    subprocess.run(["pkill", "-f", "tee.*executor.stream"],
                   capture_output=True)

    # Wait 2 seconds then force kill
    time.sleep(2)
    result = subprocess.run(
        ["pgrep", "-f", "caffeinate.*append-system-prompt-file"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        for cpid in result.stdout.strip().split("\n"):
            cpid = cpid.strip()
            if not cpid:
                continue
            parent_result = subprocess.run(
                ["ps", "-p", cpid, "-o", "ppid="],
                capture_output=True, text=True,
            )
            parent = parent_result.stdout.strip()
            if parent:
                subprocess.run(["kill", "-9", parent], capture_output=True)
            subprocess.run(["kill", "-9", cpid], capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "append-system-prompt-file"],
                       capture_output=True)


def restart() -> None:
    """Restart daemon."""
    stop()
    time.sleep(1)
    start()


def status() -> None:
    """Print daemon status."""
    print("=== heysquid Daemon Status ===\n")

    # Listeners
    print("--- Listeners ---")
    services = {
        "com.heysquid.watcher": ("TG", "Telegram"),
        "com.heysquid.slack": ("SL", "Slack"),
        "com.heysquid.discord": ("DC", "Discord"),
    }
    for label_name, (prefix, display) in services.items():
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True,
        )
        if label_name in result.stdout:
            print(f"  [{prefix}] {display}: running")
        else:
            print(f"  [{prefix}] {display}: stopped")

    # Scheduler
    print("\n--- Scheduler ---")
    result = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    if "com.heysquid.scheduler" in result.stdout:
        print("  Status: running")
    else:
        print("  Status: stopped")

    # Processes
    print("\n--- Processes ---")
    processes = {
        "executor.sh": "bash.*executor.sh",
        "Claude Code": "caffeinate.*append-system-prompt-file",
    }
    for name, pattern in processes.items():
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True)
        state = "running" if result.returncode == 0 else "idle"
        print(f"  {name}: {state}")

    # Dashboard
    print("\n--- Dashboard Server ---")
    result = subprocess.run(["lsof", "-i", ":8420"], capture_output=True)
    if result.returncode == 0:
        print("  Status: running (http://localhost:8420/dashboard.html)")
    else:
        print("  Status: stopped")

    # Lock files
    print("\n--- Lock Files ---")
    lock_file = DATA_DIR / "executor.lock"
    if lock_file.exists():
        print(f"  executor.lock: exists ({lock_file.read_text().strip()})")
    else:
        print("  executor.lock: none")

    working_file = DATA_DIR / "working.json"
    if working_file.exists():
        print("  working.json: exists")
    else:
        print("  working.json: none")

    # Registered automations + skills
    print("\n--- Registered Automations ---")
    try:
        from heysquid.automations import discover_automations
        autos = discover_automations()
        if not autos:
            print("  (no registered automations)")
        else:
            for name, meta in autos.items():
                trigger = meta.get("trigger", "?")
                schedule = meta.get("schedule", "")
                desc = meta.get("description", "")
                info = f"{trigger}"
                if schedule:
                    info += f" @ {schedule}"
                print(f"  {name}: {desc} [{info}]")
    except Exception:
        print("  (failed to list automations)")

    print("\n--- Registered Skills ---")
    try:
        from heysquid.skills._base import discover_skills
        skills = discover_skills()
        if not skills:
            print("  (no registered skills)")
        else:
            for name, meta in skills.items():
                trigger = meta.get("trigger", "?")
                desc = meta.get("description", "")
                print(f"  {name}: {desc} [{trigger}]")
    except Exception:
        print("  (failed to list skills)")


def logs(follow: bool = False) -> None:
    """Print logs."""
    log_file = LOGS_DIR / "executor.log"
    if not log_file.exists():
        print("(no logs)")
        return

    if follow:
        os.execvp("tail", ["tail", "-f", str(log_file)])
    else:
        # Last 30 lines
        with open(log_file) as f:
            lines = f.readlines()
        for line in lines[-30:]:
            print(line, end="")
