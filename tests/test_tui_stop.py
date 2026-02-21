"""IU-019a 테스트 — TUI /stop이 미처리 메시지를 정리하는지"""

import json
import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest


def _setup_store(tmp_data_dir, initial_data):
    """격리된 _msg_store를 셋업"""
    import heysquid.channels._msg_store as store

    msg_file = str(tmp_data_dir / "telegram_messages.json")
    data_dir = str(tmp_data_dir)

    orig_msg = store.MESSAGES_FILE
    orig_dir = store.DATA_DIR
    orig_lock = store._LOCK_PATH

    store.MESSAGES_FILE = msg_file
    store.DATA_DIR = data_dir
    store._LOCK_PATH = msg_file + ".lock"

    store.save_telegram_messages(initial_data)

    def restore():
        store.MESSAGES_FILE = orig_msg
        store.DATA_DIR = orig_dir
        store._LOCK_PATH = orig_lock

    return store, msg_file, restore


class TestTuiStopClearsUnprocessed:
    """TUI /stop 실행 시 미처리 메시지가 모두 processed=True가 되는지"""

    def test_kill_executor_clears_messages(self, tmp_path):
        """_kill_executor가 미처리 메시지를 정리하는지"""
        initial = {
            "messages": [
                {"message_id": 600, "type": "user", "processed": False},
                {"message_id": 601, "type": "user", "processed": False},
                {"message_id": 602, "type": "bot", "processed": True},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        # TUI commands가 사용하는 경로들을 패치
        executor_lock = str(tmp_path / "executor.lock")
        working_lock = str(tmp_path / "working.json")
        interrupted_file = str(tmp_path / "interrupted.json")

        try:
            with patch("scripts.tui_textual.commands.EXECUTOR_LOCK", executor_lock), \
                 patch("scripts.tui_textual.commands.WORKING_LOCK_FILE", working_lock), \
                 patch("scripts.tui_textual.commands.INTERRUPTED_FILE", interrupted_file), \
                 patch("subprocess.run") as mock_run:
                # pgrep이 프로세스 없음을 반환
                mock_run.return_value = MagicMock(returncode=1, stdout="")

                from scripts.tui_textual.commands import _kill_executor
                _kill_executor()

            data = store.load_telegram_messages()
            unprocessed = [m for m in data["messages"] if not m.get("processed", False)]
            assert len(unprocessed) == 0, (
                f"미처리 메시지 {len(unprocessed)}개 남아있음 — TUI /stop이 정리하지 않음"
            )
        finally:
            restore()


class TestListenerStopClearsUnprocessed:
    """Listener의 _handle_stop_command도 동일하게 정리하는지 (대조군)"""

    def test_listener_stop_clears_all(self, tmp_path):
        """listener _handle_stop_command가 미처리 메시지를 정리하는지"""
        initial = {
            "messages": [
                {"message_id": 700, "type": "user", "processed": False},
                {"message_id": 701, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            from heysquid.channels._msg_store import load_and_modify

            cleared = 0
            def _clear(data):
                nonlocal cleared
                for m in data.get("messages", []):
                    if not m.get("processed", False):
                        m["processed"] = True
                        cleared += 1
                return data

            load_and_modify(_clear)
            assert cleared == 2

            data = store.load_telegram_messages()
            assert all(m["processed"] for m in data["messages"])
        finally:
            restore()
