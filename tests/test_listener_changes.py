"""IU-018 test — Verify listener checkmark ✓ is not saved to messages.json"""

import ast
import inspect
import textwrap

import pytest


class TestCheckmarkNotSaved:
    """Code-level verification that checkmark ✓ is not saved to messages.json"""

    def test_no_save_bot_response_import(self):
        """telegram_listener.py should not import save_bot_response"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener)

        # save_bot_response should not be in import lines
        import_lines = [
            line.strip()
            for line in source.split("\n")
            if "import" in line and "save_bot_response" in line
        ]
        assert len(import_lines) == 0, (
            f"save_bot_response is still imported: {import_lines}"
        )

    def test_no_save_bot_response_call_in_fetch(self):
        """fetch_new_messages should not call save_bot_response"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener.fetch_new_messages)
        assert "save_bot_response" not in source, (
            "save_bot_response call remains in fetch_new_messages"
        )

    def test_checkmark_comment_exists(self):
        """Checkmark send code should have a 'not saved' comment"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener.fetch_new_messages)
        assert "not saved" in source.lower() or "noise" in source.lower() or "저장하지 않음" in source or "노이즈 방지" in source, (
            "No comment found indicating intentional non-saving of checkmark"
        )


class TestRetryUnprocessedUsesFlock:
    """Verify _retry_unprocessed uses load_and_modify"""

    def test_uses_load_and_modify(self):
        """_retry_unprocessed source should contain load_and_modify call"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._retry_unprocessed)
        assert "load_and_modify" in source, (
            "_retry_unprocessed does not use load_and_modify"
        )

    def test_no_direct_save_messages(self):
        """_retry_unprocessed should not call save_messages directly"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._retry_unprocessed)
        assert "save_messages(" not in source, (
            "_retry_unprocessed calls save_messages directly — should use load_and_modify"
        )


class TestHandleStopUsesFlock:
    """Verify _handle_stop_command uses load_and_modify"""

    def test_uses_load_and_modify(self):
        """_handle_stop_command source should contain load_and_modify call"""
        import heysquid.channels.telegram_listener as listener

        source = inspect.getsource(listener._handle_stop_command)
        assert "load_and_modify" in source, (
            "_handle_stop_command does not use load_and_modify"
        )
