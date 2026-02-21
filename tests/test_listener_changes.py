"""IU-018 테스트 — Listener ✓ 수신 확인이 messages.json에 저장하지 않는지"""

import ast
import inspect
import textwrap

import pytest


class TestCheckmarkNotSaved:
    """수신 확인 ✓가 messages.json에 저장되지 않는지 코드 레벨 검증"""

    def test_no_save_bot_response_import(self):
        """telegram_listener.py에서 save_bot_response를 import하지 않는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener)

        # save_bot_response가 import 라인에 없어야 함
        import_lines = [
            line.strip()
            for line in source.split("\n")
            if "import" in line and "save_bot_response" in line
        ]
        assert len(import_lines) == 0, (
            f"save_bot_response가 여전히 import되어 있음: {import_lines}"
        )

    def test_no_save_bot_response_call_in_fetch(self):
        """fetch_new_messages 내부에서 save_bot_response를 호출하지 않는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener.fetch_new_messages)
        assert "save_bot_response" not in source, (
            "fetch_new_messages에서 save_bot_response 호출이 남아있음"
        )

    def test_checkmark_comment_exists(self):
        """✓ 전송 코드에 '저장하지 않음' 주석이 있는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener.fetch_new_messages)
        assert "저장하지 않음" in source or "노이즈 방지" in source, (
            "수신 확인 비저장 의도를 명시하는 주석이 없음"
        )


class TestRetryUnprocessedUsesFlock:
    """_retry_unprocessed가 load_and_modify를 사용하는지"""

    def test_uses_load_and_modify(self):
        """_retry_unprocessed 소스에 load_and_modify 호출이 있는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._retry_unprocessed)
        assert "load_and_modify" in source, (
            "_retry_unprocessed가 load_and_modify를 사용하지 않음"
        )

    def test_no_direct_save_messages(self):
        """_retry_unprocessed에서 save_messages를 직접 호출하지 않는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._retry_unprocessed)
        assert "save_messages(" not in source, (
            "_retry_unprocessed가 save_messages를 직접 호출 — load_and_modify를 써야 함"
        )


class TestHandleStopUsesFlock:
    """_handle_stop_command가 load_and_modify를 사용하는지"""

    def test_uses_load_and_modify(self):
        """_handle_stop_command 소스에 load_and_modify 호출이 있는지"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._handle_stop_command)
        assert "load_and_modify" in source, (
            "_handle_stop_command가 load_and_modify를 사용하지 않음"
        )
