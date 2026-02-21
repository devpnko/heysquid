"""IU-015/016 테스트 — _msg_store 원자적 쓰기 + flock 잠금"""

import json
import os
import tempfile
import threading
import time
from unittest.mock import patch

import pytest


# ── 모듈 경로 패치를 위한 헬퍼 ──────────────────────────────────

def _make_store(tmp_data_dir):
    """격리된 환경에서 _msg_store 함수들을 반환"""
    msg_file = str(tmp_data_dir / "telegram_messages.json")
    data_dir = str(tmp_data_dir)

    # 모듈 레벨 상수를 패치하며 import
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


# ── IU-015: 원자적 쓰기 테스트 ────────────────────────────────

class TestAtomicWrite:
    """save_telegram_messages()가 tmp+fsync+rename 원자적 쓰기를 수행하는지 검증"""

    def test_save_creates_file(self, tmp_data_dir):
        """저장 후 파일이 정상적으로 생성되는지"""
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
        """저장 중간에 읽어도 불완전 JSON이 아닌지 (atomic rename)"""
        ctx = _make_store(tmp_data_dir)
        try:
            # 먼저 초기 데이터 저장
            initial = {"messages": [], "last_update_id": 0}
            ctx.save(initial)

            # 큰 데이터 저장 — rename 전까지 기존 파일이 온전해야 함
            large_data = {"messages": [{"id": i} for i in range(1000)], "last_update_id": 99}
            ctx.save(large_data)

            # 저장 후 파일이 완전한 JSON인지 확인
            with open(ctx.file, "r") as f:
                loaded = json.load(f)
            assert len(loaded["messages"]) == 1000
        finally:
            ctx.restore()

    def test_save_no_tmp_files_left(self, tmp_data_dir):
        """정상 저장 후 .json.tmp 파일이 남아있지 않아야 함"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            tmp_files = [f for f in os.listdir(str(tmp_data_dir)) if f.endswith(".json.tmp")]
            assert tmp_files == [], f"임시 파일 잔존: {tmp_files}"
        finally:
            ctx.restore()

    def test_load_returns_default_when_missing(self, tmp_data_dir):
        """파일이 없을 때 기본값 반환"""
        ctx = _make_store(tmp_data_dir)
        try:
            data = ctx.load()
            assert data["messages"] == []
            assert data["last_update_id"] == 0
            assert "cursors" in data  # 멀티채널 cursor 구조 포함
        finally:
            ctx.restore()

    def test_load_returns_default_on_corrupt_json(self, tmp_data_dir):
        """손상된 JSON일 때 기본값 반환"""
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


# ── IU-016: flock 잠금 테스트 ──────────────────────────────────

class TestFlockLocking:
    """load_and_modify()가 fcntl.flock으로 동시 접근을 직렬화하는지 검증"""

    def test_load_and_modify_basic(self, tmp_data_dir):
        """기본 R-M-W 동작"""
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
        """반환값이 수정된 데이터인지"""
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
        """10개 스레드가 동시에 메시지를 추가해도 하나도 빠지지 않는지"""
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

            assert not errors, f"스레드 오류: {errors}"

            loaded = ctx.load()
            assert len(loaded["messages"]) == N, (
                f"메시지 {N}개 예상, {len(loaded['messages'])}개 실제 — 업데이트 손실!"
            )
        finally:
            ctx.restore()

    def test_save_bot_response_uses_flock(self, tmp_data_dir):
        """save_bot_response가 flock을 사용하는지 (load_and_modify 경유)"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            ctx.save_bot_response(
                chat_id=12345,
                text="테스트 응답",
                reply_to_message_ids=[100],
                files=None,
                channel="system",
            )

            loaded = ctx.load()
            assert len(loaded["messages"]) == 1
            assert loaded["messages"][0]["type"] == "bot"
            assert loaded["messages"][0]["text"] == "테스트 응답"
            assert loaded["messages"][0]["reply_to"] == [100]
        finally:
            ctx.restore()

    def test_concurrent_save_bot_response(self, tmp_data_dir):
        """5개 스레드가 동시에 save_bot_response해도 모두 저장되는지"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})

            N = 5
            errors = []

            def save_response(i):
                try:
                    ctx.save_bot_response(
                        chat_id=12345,
                        text=f"응답 #{i}",
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
