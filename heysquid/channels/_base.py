"""heysquid.channels._base — abstract channel adapter + listener."""

import os
import subprocess
from abc import ABC, abstractmethod

from ._msg_store import load_and_modify


class ChannelAdapter(ABC):
    """Base class for messaging channel integrations."""

    @abstractmethod
    def send_message(self, chat_id, text, **kwargs):
        ...

    @abstractmethod
    def send_file(self, chat_id, file_path, **kwargs):
        ...


class ChannelListener(ABC):
    """Base class for channel message listeners."""

    channel_name: str  # "telegram", "slack", "discord"

    @abstractmethod
    async def fetch_new_messages(self):
        """Poll/receive new messages. Returns: count received, None=error"""
        ...

    @abstractmethod
    async def handle_stop_command(self, msg_data: dict):
        """Handle stop command"""
        ...

    @abstractmethod
    async def listen_loop(self):
        """Main loop"""
        ...

    def save_message(self, message_data: dict):
        """Common: Save message to messages.json (flock atomic)"""
        def _append(data):
            existing_ids = {m["message_id"] for m in data.get("messages", [])}
            if message_data["message_id"] not in existing_ids:
                data["messages"].append(message_data)
            return data
        load_and_modify(_append)


def trigger_executor():
    """Run executor.sh as a background process (auto-cleanup stale locks + atomic preemption)

    Common function: used by all channel listeners.

    Dedup check order:
    1. Check if the PID in executor.pid is alive (os.kill(pid, 0))
    2. pgrep -f "append-system-prompt-file" (caffeinate process)
    Both must fail to be considered a stale lock.

    NOTE: Claude Code rewrites its cmdline to "claude" after startup, so
    pgrep alone may not detect a running PM session.
    The executor.pid-based check is the primary defense.
    """
    from ..paths import EXECUTOR_LOCK_FILE
    from ..config import PROJECT_ROOT_STR as PROJECT_ROOT

    lockfile = EXECUTOR_LOCK_FILE
    executor_pidfile = os.path.join(PROJECT_ROOT, "data", "executor.pid")

    if os.path.exists(lockfile):
        # Primary: Verify process liveness via executor.pid
        if os.path.exists(executor_pidfile):
            try:
                with open(executor_pidfile) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)  # signal 0 = liveness check only (does not kill)
                # Check for zombie (defunct) process — os.kill(0) succeeds on zombies
                ps_result = subprocess.run(
                    ["ps", "-o", "state=", "-p", str(pid)],
                    capture_output=True, text=True,
                )
                state = ps_result.stdout.strip()
                if state.startswith("Z"):
                    print(f"[TRIGGER] executor PID {pid} is zombie — cleaning up")
                    raise ProcessLookupError("zombie process")
                print(f"[TRIGGER] executor already running (PID {pid}) — skipping")
                return
            except (ProcessLookupError, ValueError, OSError):
                pass  # PID dead or file corrupted — fall through

        # Secondary: pgrep fallback (detect caffeinate process)
        has_claude = subprocess.run(
            ["pgrep", "-f", "append-system-prompt-file"],
            capture_output=True,
        ).returncode == 0
        if has_claude:
            print("[TRIGGER] executor already running (pgrep) — skipping")
            return

        # Both checks failed — stale lock
        try:
            os.remove(lockfile)
            print("[TRIGGER] stale executor.lock removed")
        except OSError:
            pass
        try:
            os.remove(executor_pidfile)
        except OSError:
            pass

    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, f"pre-lock by listener PID {os.getpid()}\n".encode())
        os.close(fd)
    except FileExistsError:
        print("[TRIGGER] another trigger already acquired the lock — skipping")
        return

    executor = os.path.join(PROJECT_ROOT, "scripts", "executor.sh")
    if not os.path.exists(executor):
        print(f"[ERROR] executor.sh not found: {executor}")
        try:
            os.remove(lockfile)
        except OSError:
            pass
        return

    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "executor.log")

    print("[TRIGGER] launching executor.sh in background!")
    try:
        with open(log_file, "a") as lf:
            subprocess.Popen(
                ["bash", executor],
                stdout=lf,
                stderr=lf,
                cwd=PROJECT_ROOT,
                start_new_session=True,
            )
    except Exception as e:
        # H-9: Clean up lock file on Popen failure
        print(f"[ERROR] executor.sh launch failed: {e}")
        try:
            os.remove(lockfile)
        except OSError:
            pass
