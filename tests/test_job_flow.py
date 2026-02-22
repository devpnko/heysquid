"""IU-016 적용 테스트 — mark_done_telegram이 flock을 사용하는지"""

import json
import os
import threading
from unittest.mock import patch

import pytest


def _setup_store(tmp_data_dir, initial_data):
    """격리된 _msg_store를 셋업하고 함수 반환"""
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
    """mark_done_telegram이 flock을 경유하여 processed를 마킹하는지"""

    def test_single_message_marked(self, tmp_path):
        """단일 메시지 처리 완료 마킹"""
        initial = {
            "messages": [
                {"message_id": 100, "type": "user", "processed": False},
                {"message_id": 101, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        try:
            # _working_lock의 함수들을 모킹 (파일 경로 의존성 회피)
            with patch("heysquid.core._job_flow.load_new_instructions", return_value=[]), \
                 patch("heysquid.core._job_flow.clear_new_instructions"):
                from heysquid.core._job_flow import mark_done_telegram
                mark_done_telegram(100)

            data = store.load_telegram_messages()
            msg100 = next(m for m in data["messages"] if m["message_id"] == 100)
            msg101 = next(m for m in data["messages"] if m["message_id"] == 101)

            assert msg100["processed"] is True, "msg 100이 processed가 아님"
            assert msg101["processed"] is False, "msg 101이 잘못 processed됨"
        finally:
            restore()

    def test_multiple_messages_marked(self, tmp_path):
        """리스트로 전달한 여러 메시지 처리 완료"""
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
        """작업 중 추가된 지시사항도 함께 처리되는지"""
        initial = {
            "messages": [
                {"message_id": 300, "type": "user", "processed": False},
                {"message_id": 301, "type": "user", "processed": False},
            ],
            "last_update_id": 0,
        }
        store, msg_file, restore = _setup_store(tmp_path, initial)

        new_insts = [{"message_id": 301, "text": "추가 지시"}]

        try:
            with patch("heysquid.core._job_flow.load_new_instructions", return_value=new_insts), \
                 patch("heysquid.core._job_flow.clear_new_instructions"):
                from heysquid.core._job_flow import mark_done_telegram
                mark_done_telegram(300)

            data = store.load_telegram_messages()
            assert all(m["processed"] for m in data["messages"]), (
                "새 지시사항 메시지(301)가 함께 처리되지 않음"
            )
        finally:
            restore()


class TestReplyTelegramFlock:
    """reply_telegram이 flock을 경유하여 processed/rollback하는지"""

    def test_processed_marking_on_success(self, tmp_path):
        """전송 성공 시 processed가 True가 되는지"""
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

            # 봇 응답도 저장되었는지
            bot_msgs = [m for m in data["messages"] if m["type"] == "bot"]
            assert len(bot_msgs) == 1
        finally:
            restore()

    def test_processed_rollback_on_failure(self, tmp_path):
        """전송 실패 시 processed가 False로 롤백되는지"""
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
                success = reply_telegram(12345, 500, "실패할 메시지")

            assert success is False
            data = store.load_telegram_messages()
            user_msg = next(m for m in data["messages"] if m["message_id"] == 500)
            assert user_msg["processed"] is False, "전송 실패인데 processed가 롤백되지 않음"
        finally:
            restore()
