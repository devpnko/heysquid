"""IU-016 applied test — verify mark_done_telegram uses flock"""

import json
import os
import threading
from unittest.mock import patch

import pytest


def _setup_store(tmp_data_dir, initial_data):
    """Set up isolated _msg_store and return functions"""
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


class TestMarkDoneTelegram:
    """Verify mark_done_telegram marks processed via flock"""

    def test_single_message_marked(self, tmp_path):
        """Mark single message as processed"""
        initial = {
            "messages": [
                {"message_id": 100, "type": "user", "processed": False},
                {"message_id": 101, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            # Mock _working_lock functions (avoid file path dependencies)
            with patch("heysquid.core._job_flow.load_new_instructions", return_value=[]), \
                 patch("heysquid.core._job_flow.clear_new_instructions"):
                from heysquid.core._job_flow import mark_done_telegram
                mark_done_telegram(100)

            data = store.load_telegram_messages()
            msg100 = next(m for m in data["messages"] if m["message_id"] == 100)
            msg101 = next(m for m in data["messages"] if m["message_id"] == 101)

            assert msg100["processed"] is True, "msg 100 is not processed"
            assert msg101["processed"] is False, "msg 101 incorrectly marked as processed"
        finally:
            restore()

    def test_multiple_messages_marked(self, tmp_path):
        """Mark multiple messages as processed via list"""
        initial = {
            "messages": [
                {"message_id": 200, "type": "user", "processed": False},
                {"message_id": 201, "type": "user", "processed": False},
                {"message_id": 202, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            with patch("heysquid.core._job_flow.load_new_instructions", return_value=[]), \
                 patch("heysquid.core._job_flow.clear_new_instructions"):
                from heysquid.core._job_flow import mark_done_telegram
                mark_done_telegram([200, 201])

            data = store.load_telegram_messages()
            assert data["messages"][0]["processed"] is True
            assert data["messages"][1]["processed"] is True
            assert data["messages"][2]["processed"] is False
        finally:
            restore()

    def test_with_new_instructions(self, tmp_path):
        """New instructions added during work should also be processed"""
        initial = {
            "messages": [
                {"message_id": 300, "type": "user", "processed": False},
                {"message_id": 301, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        new_insts = [{"message_id": 301, "text": "additional instruction"}]

        try:
            with patch("heysquid.core._job_flow.load_new_instructions", return_value=new_insts), \
                 patch("heysquid.core._job_flow.clear_new_instructions"):
                from heysquid.core._job_flow import mark_done_telegram
                mark_done_telegram(300)

            data = store.load_telegram_messages()
            assert all(m["processed"] for m in data["messages"]), (
                "New instruction message (301) was not processed together"
            )
        finally:
            restore()


class TestReplyTelegramFlock:
    """Verify reply_telegram handles processed/rollback via flock"""

    def test_processed_marking_on_success(self, tmp_path):
        """processed should be True on successful send"""
        initial = {
            "messages": [
                {"message_id": 400, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            with patch("heysquid.channels.telegram.send_message_sync", return_value=True):
                from heysquid.core.hub import reply_telegram
                success = reply_telegram(12345, 400, "안녕!")

            assert success is True
            data = store.load_telegram_messages()
            user_msg = next(m for m in data["messages"] if m["message_id"] == 400)
            assert user_msg["processed"] is True

            # Verify bot response was also saved
            bot_msgs = [m for m in data["messages"] if m["type"] == "bot"]
            assert len(bot_msgs) == 1
        finally:
            restore()

    def test_processed_rollback_on_failure(self, tmp_path):
        """processed should be rolled back to False on send failure"""
        initial = {
            "messages": [
                {"message_id": 500, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            with patch("heysquid.channels.telegram.send_message_sync", return_value=False):
                from heysquid.core.hub import reply_telegram
                success = reply_telegram(12345, 500, "message that will fail")

            assert success is False
            data = store.load_telegram_messages()
            user_msg = next(m for m in data["messages"] if m["message_id"] == 500)
            assert user_msg["processed"] is False, "processed was not rolled back despite send failure"
        finally:
            restore()
