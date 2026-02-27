"""IU-019 test — executor lock preemption + stale timeout unification"""

import os
import subprocess
import re

import pytest


# ── executor.sh stale timeout verification ────────────────────────────

class TestExecutorShStaleTimeout:
    """Verify executor.sh stale timeout is 1800 seconds (30 minutes)"""

    EXECUTOR_SH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "executor.sh")

    def test_stale_timeout_is_1800(self):
        """executor.sh stale threshold should be 1800 (30 minutes)"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # Extract LOG_AGE -gt value
        match = re.search(r'LOG_AGE.*-gt\s+(\d+)', content)
        assert match, "Cannot find LOG_AGE stale threshold pattern in executor.sh"
        timeout = int(match.group(1))
        assert timeout == 1800, f"stale timeout is {timeout}s — expected 1800s (30 min)"

    def test_stale_timeout_matches_working_lock(self):
        """executor.sh stale timeout should match WORKING_LOCK_TIMEOUT"""
        from heysquid.core.paths import WORKING_LOCK_TIMEOUT

        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        match = re.search(r'LOG_AGE.*-gt\s+(\d+)', content)
        executor_timeout = int(match.group(1))

        assert executor_timeout == WORKING_LOCK_TIMEOUT, (
            f"executor.sh({executor_timeout}s) != WORKING_LOCK_TIMEOUT({WORKING_LOCK_TIMEOUT}s)"
        )

    def test_no_crash_recovery_lock_deletion(self):
        """executor.sh step 2 should not delete the lock"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # rm -f "$LOCKFILE" should NOT exist in step 2 section
        # (rm after stale kill in step 1 is OK)
        # step 2 starts after the "Lock file check" comment
        step2_start = content.find("# 2. Lock file check")
        if step2_start < 0:
            step2_start = content.find("# 2. Lock 파일 확인")
        step3_start = content.find("# 3. Quick message check")
        if step3_start < 0:
            step3_start = content.find("# 3. 빠른 메시지 확인")
        assert step2_start > 0 and step3_start > 0

        step2_section = content[step2_start:step3_start]
        assert 'rm -f "$LOCKFILE"' not in step2_section, (
            "lock deletion found in step 2 — conflicts with listener pre-lock"
        )

    def test_no_message_exit_cleans_lock(self):
        """Lock should be cleaned up before exit when no messages"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # NO_MESSAGE section should contain rm -f "$LOCKFILE"
        no_msg_start = content.find("[NO_MESSAGE]")
        assert no_msg_start > 0
        # Section from NO_MESSAGE to exit 0
        no_msg_section = content[no_msg_start:content.find("exit 0", no_msg_start) + 10]
        assert 'rm -f "$LOCKFILE"' in no_msg_section, (
            "No lock cleanup found in NO_MESSAGE exit"
        )


# ── _trigger_executor() atomic lock preemption verification ──────────────────

class TestTriggerExecutorLock:
    """Verify trigger_executor() preempts lock atomically using O_EXCL"""

    def test_trigger_creates_lock_atomically(self, tmp_path):
        """trigger_executor should create lock first using O_EXCL"""
        from unittest.mock import patch
        from heysquid.channels._base import trigger_executor

        # Patch paths
        lockfile = str(tmp_path / "executor.lock")

        # Create scripts/ directory and executor.sh
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        with open(str(scripts_dir / "executor.sh"), "w") as f:
            f.write("#!/bin/bash\nexit 0\n")

        with patch("heysquid.paths.EXECUTOR_LOCK_FILE", lockfile), \
             patch("heysquid.config.PROJECT_ROOT_STR", str(tmp_path)):
            trigger_executor()
            assert os.path.exists(lockfile), "lock file was not created"

            with open(lockfile, "r") as f:
                content = f.read()
            assert "pre-lock" in content, "pre-lock marker not found"

    def test_trigger_skips_when_lock_exists(self, tmp_path, capsys):
        """Second trigger should skip when lock already exists"""
        lockfile = str(tmp_path / "executor.lock")

        # Create lock first (simulating another trigger already holding it)
        with open(lockfile, "w") as f:
            f.write("pre-lock by another trigger\n")

        # Direct O_EXCL test
        fd = None
        try:
            fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            pytest.fail("O_EXCL succeeded — lock should already exist")
        except FileExistsError:
            pass  # Expected failure
        finally:
            if fd is not None:
                os.close(fd)
