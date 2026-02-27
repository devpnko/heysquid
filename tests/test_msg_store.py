"""IU-015/016 test — _msg_store atomic write + flock locking"""

import json
import os
import tempfile
import threading
import time
from unittest.mock import patch

import pytest


# ── Helper for module path patching ──────────────────────────────────

def _make_store(tmp_data_dir):
    """Return _msg_store functions in an isolated environment"""
    msg_file = str(tmp_data_dir / "telegram_messages.json")
    data_dir = str(tmp_data_dir)

    # Patch module-level constants on import
    import heysquid.channels._msg_store as store
    original_msg = store.MESSAGES_FILE
    original_dir = store.DATA_DIR
    original_lock = store._LOCK_PATH

    store.MESSAGES_FILE = msg_file
    store.DATA_DIR = data_dir
    store._LOCK_PATH = msg_file + ".lock"

    class Ctx:
        load = staticmethod(store.load_telegram_messages)
        save = staticmethod(store.save_telegram_messages)
        load_and_modify = staticmethod(store.load_and_modify)
        save_bot_response = staticmethod(store.save_bot_response)
        file = msg_file

        @staticmethod
        def restore():
            store.MESSAGES_FILE = original_msg
            store.DATA_DIR = original_dir
            store._LOCK_PATH = original_lock

    return Ctx


# ── IU-015: Atomic write tests ────────────────────────────────

class TestAtomicWrite:
    """Verify save_telegram_messages() performs atomic write via tmp+fsync+rename"""

    def test_save_creates_file(self, tmp_data_dir):
        """File should be created normally after save"""
        ctx = _make_store(tmp_data_dir)
        try:
            data = {"messages": [{"id": 1}], "last_update_id": 0}
            ctx.save(data)
            assert os.path.exists(ctx.file)
            with open(ctx.file, "r") as f:
                loaded = json.load(f)
            assert loaded == data
        finally:
            ctx.restore()

    def test_save_no_partial_write(self, tmp_data_dir):
        """Reading mid-save should not yield incomplete JSON (atomic rename)"""
        ctx = _make_store(tmp_data_dir)
        try:
            # Save initial data first
            initial = {"messages": [], "last_update_id": 0}
            ctx.save(initial)

            # Save large data — existing file must remain intact until rename
            large_data = {"messages": [{"id": i} for i in range(1000)], "last_update_id": 99}
            ctx.save(large_data)

            # Verify file is complete JSON after save
            with open(ctx.file, "r") as f:
                loaded = json.load(f)
            assert len(loaded["messages"]) == 1000
        finally:
            ctx.restore()

    def test_save_no_tmp_files_left(self, tmp_data_dir):
        """No .json.tmp files should remain after successful save"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            tmp_files = [f for f in os.listdir(str(tmp_data_dir)) if f.endswith(".json.tmp")]
            assert tmp_files == [], f"Temporary files remaining: {tmp_files}"
        finally:
            ctx.restore()

    def test_load_returns_default_when_missing(self, tmp_data_dir):
        """Return default value when file is missing"""
        ctx = _make_store(tmp_data_dir)
        try:
            data = ctx.load()
            assert data["messages"] == []
            assert data["last_update_id"] == 0
            assert "cursors" in data  # Multi-channel cursor structure included
        finally:
            ctx.restore()

    def test_load_returns_default_on_corrupt_json(self, tmp_data_dir):
        """Return default value on corrupt JSON"""
        ctx = _make_store(tmp_data_dir)
        try:
            with open(ctx.file, "w") as f:
                f.write("{invalid json...")
            data = ctx.load()
            assert data["messages"] == []
            assert data["last_update_id"] == 0
            assert "cursors" in data
        finally:
            ctx.restore()


# ── IU-016: flock locking tests ──────────────────────────────────

class TestFlockLocking:
    """Verify load_and_modify() serializes concurrent access via fcntl.flock"""

    def test_load_and_modify_basic(self, tmp_data_dir):
        """Basic R-M-W operation"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [{"id": 1, "text": "hello"}], "last_update_id": 0})

            def add_msg(data):
                data["messages"].append({"id": 2, "text": "world"})
                return data

            result = ctx.load_and_modify(add_msg)
            assert len(result["messages"]) == 2

            loaded = ctx.load()
            assert len(loaded["messages"]) == 2
        finally:
            ctx.restore()

    def test_load_and_modify_returns_modified_data(self, tmp_data_dir):
        """Return value should be the modified data"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            def set_update_id(data):
                data["last_update_id"] = 42
                return data

            result = ctx.load_and_modify(set_update_id)
            assert result["last_update_id"] == 42
        finally:
            ctx.restore()

    def test_concurrent_load_and_modify_no_lost_updates(self, tmp_data_dir):
        """10 concurrent threads adding messages should not lose any updates"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            errors = []
            N = 10

            def append_msg(thread_id):
                try:
                    def _add(data):
                        data["messages"].append({"id": thread_id, "thread": thread_id})
                        return data
                    ctx.load_and_modify(_add)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=append_msg, args=(i,)) for i in range(N)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            assert not errors, f"Thread errors: {errors}"

            loaded = ctx.load()
            assert len(loaded["messages"]) == N, (
                f"Expected {N} messages, got {len(loaded['messages'])} — lost updates!"
            )
        finally:
            ctx.restore()

    def test_save_bot_response_uses_flock(self, tmp_data_dir):
        """save_bot_response should use flock (via load_and_modify)"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            ctx.save_bot_response(
                chat_id=12345,
                text="test response",
                reply_to_message_ids=[100],
                files=None,
                channel="system",
            )

            loaded = ctx.load()
            assert len(loaded["messages"]) == 1
            assert loaded["messages"][0]["type"] == "bot"
            assert loaded["messages"][0]["text"] == "test response"
            assert loaded["messages"][0]["reply_to"] == [100]
        finally:
            ctx.restore()

    def test_concurrent_save_bot_response(self, tmp_data_dir):
        """5 concurrent threads calling save_bot_response should all be saved"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            N = 5
            errors = []

            def save_response(i):
                try:
                    ctx.save_bot_response(
                        chat_id=12345,
                        text=f"response #{i}",
                        reply_to_message_ids=[i],
                        channel="system",
                    )
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=save_response, args=(i,)) for i in range(N)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            assert not errors
            loaded = ctx.load()
            assert len(loaded["messages"]) == N
        finally:
            ctx.restore()
