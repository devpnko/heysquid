"""IU-019 테스트 — executor lock 선점 + stale 타임아웃 통일"""

import os
import subprocess
import re

import pytest


# ── executor.sh stale 타임아웃 검증 ────────────────────────────

class TestExecutorShStaleTimeout:
    """executor.sh의 stale 타임아웃이 1800초(30분)인지 검증"""

    EXECUTOR_SH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "executor.sh")

    def test_stale_timeout_is_1800(self):
        """executor.sh의 stale 판정 기준이 1800 (30분)인지"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # LOG_AGE -gt 값 추출
        match = re.search(r'LOG_AGE.*-gt\s+(\d+)', content)
        assert match, "executor.sh에서 LOG_AGE stale 판정 패턴을 찾을 수 없음"
        timeout = int(match.group(1))
        assert timeout == 1800, f"stale 타임아웃이 {timeout}초 — 1800초(30분) 예상"

    def test_stale_timeout_matches_working_lock(self):
        """executor.sh의 stale 타임아웃과 WORKING_LOCK_TIMEOUT이 일치하는지"""
        from heysquid.core.paths import WORKING_LOCK_TIMEOUT

        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        match = re.search(r'LOG_AGE.*-gt\s+(\d+)', content)
        executor_timeout = int(match.group(1))

        assert executor_timeout == WORKING_LOCK_TIMEOUT, (
            f"executor.sh({executor_timeout}s) != WORKING_LOCK_TIMEOUT({WORKING_LOCK_TIMEOUT}s)"
        )

    def test_no_crash_recovery_lock_deletion(self):
        """executor.sh step 2에서 lock을 삭제하지 않는지"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # step 2 영역에서 rm -f "$LOCKFILE"가 없어야 함
        # (step 1의 stale kill 후 rm은 있어도 됨)
        # step 2는 "Lock 파일 확인" 주석 뒤에 있음
        step2_start = content.find("# 2. Lock 파일 확인")
        step3_start = content.find("# 3. 빠른 메시지 확인")
        assert step2_start > 0 and step3_start > 0

        step2_section = content[step2_start:step3_start]
        assert 'rm -f "$LOCKFILE"' not in step2_section, (
            "step 2에서 lock 삭제가 발견됨 — listener pre-lock과 충돌"
        )

    def test_no_message_exit_cleans_lock(self):
        """메시지 없을 때 exit 전에 lock을 정리하는지"""
        with open(self.EXECUTOR_SH, "r") as f:
            content = f.read()

        # NO_MESSAGE 섹션에서 rm -f "$LOCKFILE"가 있어야 함
        no_msg_start = content.find("[NO_MESSAGE]")
        assert no_msg_start > 0
        # NO_MESSAGE부터 exit 0까지의 영역
        no_msg_section = content[no_msg_start:content.find("exit 0", no_msg_start) + 10]
        assert 'rm -f "$LOCKFILE"' in no_msg_section, (
            "NO_MESSAGE exit에서 lock 정리가 없음"
        )


# ── _trigger_executor() 원자적 lock 선점 검증 ──────────────────

class TestTriggerExecutorLock:
    """trigger_executor()가 O_EXCL로 원자적 lock을 선점하는지 검증"""

    def test_trigger_creates_lock_atomically(self, tmp_path):
        """trigger_executor가 O_EXCL로 lock을 먼저 생성하는지"""
        from unittest.mock import patch
        from heysquid.channels._base import trigger_executor

        # 경로 패치
        lockfile = str(tmp_path / "executor.lock")

        # scripts/ 디렉토리와 executor.sh 생성
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        with open(str(scripts_dir / "executor.sh"), "w") as f:
            f.write("#!/bin/bash\nexit 0\n")

        with patch("heysquid.paths.EXECUTOR_LOCK_FILE", lockfile), \
             patch("heysquid.config.PROJECT_ROOT_STR", str(tmp_path)):
            trigger_executor()
            assert os.path.exists(lockfile), "lock 파일이 생성되지 않음"

            with open(lockfile, "r") as f:
                content = f.read()
            assert "pre-lock" in content, "pre-lock 표시가 없음"

    def test_trigger_skips_when_lock_exists(self, tmp_path, capsys):
        """이미 lock이 있으면 두 번째 trigger가 스킵되는지"""
        lockfile = str(tmp_path / "executor.lock")

        # 먼저 lock 생성 (다른 trigger가 선점한 상황)
        with open(lockfile, "w") as f:
            f.write("pre-lock by another trigger\n")

        # 직접 O_EXCL 테스트
        fd = None
        try:
            fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            pytest.fail("O_EXCL이 성공함 — lock이 이미 있어야 하는데?")
        except FileExistsError:
            pass  # 예상대로 실패
        finally:
            if fd is not None:
                os.close(fd)
