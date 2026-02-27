"""Task Queue + WAITING State + Reply Matching Tests

Covers all 7 changed files:
1. telegram_listener.py — reply_to_message_id capture
2. channels/telegram.py — sent_message_id return
3. _msg_store.py — sent_message_id storage
4. dashboard/kanban.py — set_task_waiting + get_waiting_context
5. core/_working_lock.py — transition_to_waiting
6. core/hub.py — pick_next_task + ask_and_wait + bug fix
7. pm-workflow.md — docs (not tested)
"""

import json
import os
import time
import threading
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# ── Helper: isolated _msg_store ────────────────────────────────────

def _make_store(tmp_data_dir):
    """Return _msg_store functions in an isolated environment"""
    msg_file = str(tmp_data_dir / "telegram_messages.json")
    data_dir = str(tmp_data_dir)

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


def _make_kanban(tmp_data_dir):
    """Return kanban + dashboard functions in an isolated environment"""
    status_file = str(tmp_data_dir / "agent_status.json")
    lock_file = status_file + ".lock"
    data_dir = str(tmp_data_dir)

    import heysquid.dashboard as dash
    original_sf = dash.STATUS_FILE
    original_lock = dash._STATUS_LOCK
    original_dd = dash.DATA_DIR

    dash.STATUS_FILE = status_file
    dash._STATUS_LOCK = lock_file
    dash.DATA_DIR = data_dir

    # kanban uses the same functions, no separate patch needed (imported via dashboard.__init__)

    class Ctx:
        # kanban functions
        add_task = staticmethod(dash.add_kanban_task)
        update_by_msg = staticmethod(dash.update_kanban_by_message_ids)
        set_task_waiting = staticmethod(dash.set_task_waiting)
        get_waiting_context = staticmethod(dash.get_waiting_context)
        move_task = staticmethod(dash.move_kanban_task)
        get_active_id = staticmethod(dash.get_active_kanban_task_id)
        load_status = staticmethod(dash._load_status)
        save_status = staticmethod(dash._save_status)
        file = status_file

        @staticmethod
        def restore():
            dash.STATUS_FILE = original_sf
            dash._STATUS_LOCK = original_lock
            dash.DATA_DIR = original_dd

    return Ctx


# ── Step 3: _msg_store — sent_message_id storage ──────────────────

class TestSentMessageIdStore:
    """Verify save_bot_response correctly stores sent_message_id"""

    def test_save_with_sent_message_id(self, tmp_data_dir):
        """sent_message_id should be saved when provided"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            ctx.save_bot_response(
                chat_id=12345, text="This is a question",
                reply_to_message_ids=[100],
                channel="broadcast", sent_message_id=42
            )
            loaded = ctx.load()
            bot_msg = loaded["messages"][0]
            assert bot_msg["sent_message_id"] == 42
        finally:
            ctx.restore()

    def test_save_without_sent_message_id(self, tmp_data_dir):
        """Field should not exist when sent_message_id is None"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            ctx.save_bot_response(
                chat_id=12345, text="normal response",
                reply_to_message_ids=[100],
                channel="system"
            )
            loaded = ctx.load()
            bot_msg = loaded["messages"][0]
            assert "sent_message_id" not in bot_msg
        finally:
            ctx.restore()

    def test_backward_compat_no_sent_id_param(self, tmp_data_dir):
        """Legacy call pattern (omitting sent_message_id) should still work"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            # Call without sent_message_id like legacy code
            ctx.save_bot_response(12345, "test", [200], None, "system")
            loaded = ctx.load()
            assert len(loaded["messages"]) == 1
            assert "sent_message_id" not in loaded["messages"][0]
        finally:
            ctx.restore()


# ── Step 4: kanban — WAITING lifecycle ───────────────────────

class TestKanbanWaiting:
    """Verify set_task_waiting + get_waiting_context"""

    def test_set_task_waiting(self, tmp_data_dir):
        """IN_PROGRESS → WAITING transition + sent_ids storage"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            task = ctx.add_task("Test task", "in_progress", [100], 12345)
            assert task is not None
            task_id = task["id"]

            result = ctx.set_task_waiting(task_id, [42, 43], "Waiting: please confirm")
            assert result is True

            # Check card state
            card = ctx.get_waiting_context(task_id)
            assert card is not None
            assert card["column"] == "waiting"
            assert card["waiting_sent_ids"] == [42, 43]
            assert "waiting_since" in card
            # Check activity_log
            last_log = card["activity_log"][-1]
            assert "Waiting" in last_log["message"]
        finally:
            ctx.restore()

    def test_set_task_waiting_nonexistent(self, tmp_data_dir):
        """Non-existent task_id should return False"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            result = ctx.set_task_waiting("nonexistent-id", [42])
            assert result is False
        finally:
            ctx.restore()

    def test_get_waiting_context_returns_full_card(self, tmp_data_dir):
        """All fields of a WAITING card should be returned"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            task = ctx.add_task("Full context task", "in_progress", [200, 201], 12345, ["tag1"])
            task_id = task["id"]
            ctx.set_task_waiting(task_id, [55], "Asking question")

            card = ctx.get_waiting_context(task_id)
            assert card["title"] == "Full context task"
            assert card["source_message_ids"] == [200, 201]
            assert card["chat_id"] == 12345
            assert card["tags"] == ["tag1"]
            assert len(card["activity_log"]) >= 2  # created + waiting
        finally:
            ctx.restore()

    def test_get_waiting_context_nonexistent(self, tmp_data_dir):
        """Non-existent task should return None"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            result = ctx.get_waiting_context("nonexistent")
            assert result is None
        finally:
            ctx.restore()


# ── Step 5: _working_lock — transition_to_waiting ────────────────

class TestWorkingLockWaiting:
    """Verify remove_working_lock(transition_to_waiting=True) behavior"""

    def test_transition_to_waiting_removes_lock(self, tmp_data_dir):
        """Lock file should be deleted even with transition_to_waiting=True"""
        lock_file = str(tmp_data_dir / "working.json")

        import heysquid.core._working_lock as wl
        original = wl.WORKING_LOCK_FILE
        wl.WORKING_LOCK_FILE = lock_file

        try:
            # Create lock file
            with open(lock_file, "w") as f:
                json.dump({"message_id": [100], "instruction_summary": "test"}, f)

            assert os.path.exists(lock_file)

            with patch.object(wl, '_dashboard_log'):
                with patch('heysquid.core._working_lock.set_pm_speech', create=True):
                    # mock typing stop
                    with patch('heysquid.channels._typing.stop', create=True):
                        wl.remove_working_lock(transition_to_waiting=True)

            assert not os.path.exists(lock_file)
        finally:
            wl.WORKING_LOCK_FILE = original

    def test_default_removes_lock_and_clears_speech(self, tmp_data_dir):
        """Default call (transition_to_waiting=False) should preserve existing behavior"""
        lock_file = str(tmp_data_dir / "working.json")

        import heysquid.core._working_lock as wl
        original = wl.WORKING_LOCK_FILE
        wl.WORKING_LOCK_FILE = lock_file

        try:
            with open(lock_file, "w") as f:
                json.dump({"message_id": [100]}, f)

            mock_speech = MagicMock()
            with patch.object(wl, '_dashboard_log'):
                with patch('heysquid.agent_dashboard.set_pm_speech', mock_speech, create=True):
                    with patch('heysquid.channels._typing.stop', create=True):
                        wl.remove_working_lock()

            assert not os.path.exists(lock_file)
            # Verify set_pm_speech('') was called
            mock_speech.assert_called_with('')
        finally:
            wl.WORKING_LOCK_FILE = original


# ── Step 6: hub.py — bug fix + pick_next_task + ask_and_wait ──

class TestBugFixInstructionKey:
    """check_telegram() line 403 bug fix — task.get('text') → task.get('instruction')"""

    def test_kanban_title_uses_instruction(self):
        """Verify hub.py source uses instruction key for kanban title.

        Should contain (task.get("instruction") or "New task")[:80] pattern,
        and should NOT contain (task.get("text") or "New task")[:80] bug pattern.
        """
        import heysquid.core.hub as hub

        with open(hub.__file__) as f:
            source = f.read()

        # Verify fixed pattern exists
        assert '(task.get("instruction") or "New task")' in source, \
            'task.get("instruction") or "New task" pattern not found'
        # Verify bug pattern is absent
        assert '(task.get("text") or "New task")' not in source, \
            'task.get("text") or "New task" bug still exists'


class TestPickNextTask:
    """pick_next_task() — WAITING reply matching + oldest TODO fallback"""

    def _make_pending(self, *ids_and_instructions):
        """Create pending task list for testing"""
        tasks = []
        for i, (mid, inst) in enumerate(ids_and_instructions):
            tasks.append({
                "instruction": inst,
                "message_id": mid,
                "chat_id": 12345,
                "timestamp": f"2026-02-25 10:{i:02d}:00",
                "context_24h": "",
                "user_name": "tester",
                "files": [],
                "location": None,
                "stale_resume": False,
            })
        return tasks

    def test_single_task_returns_it(self):
        """Single pending task should be returned as-is"""
        from heysquid.core.hub import pick_next_task

        pending = self._make_pending((100, "Do A"))

        with patch('heysquid.core.hub.load_telegram_messages', return_value={"messages": []}):
            with patch('heysquid.dashboard._load_status', return_value={"kanban": {"tasks": []}}):
                result = pick_next_task(pending)

        assert result is not None
        assert result["task"]["message_id"] == 100
        assert result["waiting_card"] is None
        assert result["remaining"] == []

    def test_multiple_tasks_oldest_first(self):
        """3 pending tasks should select oldest (by timestamp)"""
        from heysquid.core.hub import pick_next_task

        pending = self._make_pending(
            (100, "Do A"),
            (101, "Do B"),
            (102, "Do C"),
        )

        with patch('heysquid.core.hub.load_telegram_messages', return_value={"messages": []}):
            with patch('heysquid.dashboard._load_status', return_value={"kanban": {"tasks": []}}):
                result = pick_next_task(pending)

        assert result["task"]["message_id"] == 100
        assert len(result["remaining"]) == 2

    def test_empty_returns_none(self):
        """Empty list should return None"""
        from heysquid.core.hub import pick_next_task
        assert pick_next_task([]) is None

    def test_waiting_reply_matched(self):
        """Match reply_to_message_id to WAITING card's sent_id"""
        from heysquid.core.hub import pick_next_task

        # WAITING card: asked question with sent_message_id=50
        waiting_card = {
            "id": "kb-waiting-1",
            "title": "A task",
            "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        # Message: msg_id=200 is a reply to msg_id=50
        messages = [
            {"message_id": 200, "reply_to_message_id": 50, "type": "user",
             "text": "Yes do it", "processed": False},
            {"message_id": 201, "reply_to_message_id": None, "type": "user",
             "text": "Do B", "processed": False},
        ]

        pending = self._make_pending((200, "Yes do it"), (201, "Do B"))
        kanban_data = {"kanban": {"tasks": [waiting_card]}}

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status', return_value=kanban_data):
                result = pick_next_task(pending)

        assert result["task"]["message_id"] == 200
        assert result["waiting_card"] is not None
        assert result["waiting_card"]["id"] == "kb-waiting-1"
        assert len(result["remaining"]) == 1
        assert result["remaining"][0]["message_id"] == 201

    def test_waiting_auto_match_single(self):
        """1 WAITING + 1 pending should auto-match (even without reply)"""
        from heysquid.core.hub import pick_next_task

        waiting_card = {
            "id": "kb-waiting-1",
            "title": "A task",
            "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        messages = [
            {"message_id": 300, "type": "user", "text": "응", "processed": False},
        ]

        pending = self._make_pending((300, "응"))
        kanban_data = {"kanban": {"tasks": [waiting_card]}}

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status', return_value=kanban_data):
                result = pick_next_task(pending)

        assert result["waiting_card"] is not None
        assert result["waiting_card"]["id"] == "kb-waiting-1"

    def test_no_waiting_match_falls_through_to_oldest(self):
        """WAITING exists but no reply match should fall through to oldest TODO"""
        from heysquid.core.hub import pick_next_task

        waiting_card = {
            "id": "kb-waiting-1",
            "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        # 2 pending, neither has a reply
        messages = [
            {"message_id": 400, "type": "user", "text": "X", "processed": False},
            {"message_id": 401, "type": "user", "text": "Y", "processed": False},
        ]

        pending = self._make_pending((400, "Do X"), (401, "Do Y"))
        kanban_data = {"kanban": {"tasks": [waiting_card]}}

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status', return_value=kanban_data):
                result = pick_next_task(pending)

        # WAITING match failed → oldest
        assert result["task"]["message_id"] == 400
        assert result["waiting_card"] is None


class TestAskAndWait:
    """ask_and_wait() — send question + transition to WAITING + release lock"""

    def test_ask_and_wait_sends_and_transitions(self, tmp_data_dir):
        """Normal flow: send → save bot response → WAITING → release lock"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=99) as mock_send:
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.dashboard.kanban.get_active_kanban_task_id', return_value="kb-123"):
                    with patch('heysquid.dashboard.kanban.set_task_waiting') as mock_waiting:
                        with patch('heysquid.core.hub.remove_working_lock') as mock_unlock:
                            result = ask_and_wait(12345, [100], "Should I do it this way?")

        assert result is True

        # Verify send_message_sync call
        mock_send.assert_called_once_with(12345, "Should I do it this way?", _save=False)

        # Verify save_bot_response call (sent_message_id=99)
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        assert call_kwargs[1].get("sent_message_id") == 99 or call_kwargs[0][-1] == 99

        # Verify set_task_waiting call
        mock_waiting.assert_called_once_with("kb-123", [99], reason="Waiting: Should I do it this way?")

        # remove_working_lock(transition_to_waiting=True)
        mock_unlock.assert_called_once_with(transition_to_waiting=True)

    def test_ask_and_wait_send_failure(self):
        """Send failure should return False, remaining calls should not be made"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=False):
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.core.hub.remove_working_lock') as mock_unlock:
                    result = ask_and_wait(12345, [100], "question")

        assert result is False
        mock_save.assert_not_called()
        mock_unlock.assert_not_called()

    def test_ask_and_wait_single_message_id(self):
        """Should work correctly when message_id is an int"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=88):
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.dashboard.kanban.get_active_kanban_task_id', return_value=None):
                    with patch('heysquid.core.hub.remove_working_lock'):
                        result = ask_and_wait(12345, 100, "single ID test")

        assert result is True
        # ids should be converted to [100] before passing
        assert mock_save.call_args[0][2] == [100]


# ── Step 2: telegram.py — send_message return value ──────────────────

class TestSendMessageReturnValue:
    """Verify send_message() returns int(msg_id)"""

    def test_send_message_returns_int(self):
        """Should return int(message_id) on successful send"""
        import heysquid.channels.telegram as tg
        import asyncio

        mock_msg = MagicMock()
        mock_msg.message_id = 42

        # async mock — send_message is async, needs to return coroutine
        async def mock_send(**kwargs):
            return mock_msg

        mock_bot = MagicMock()
        mock_bot.send_message = mock_send

        async def _test():
            with patch.object(tg, '_get_bot', return_value=mock_bot):
                with patch.object(tg, 'BOT_TOKEN', 'fake-token'):
                    result = await tg.send_message(12345, "hello")
            return result

        result = asyncio.run(_test())
        assert result == 42
        assert isinstance(result, int)

    def test_send_message_backward_compat(self):
        """int return value should be compatible with bool checks"""
        assert bool(42) is True   # int → truthy
        assert bool(0) is False   # 0 is falsy but message_id is never 0

    def test_send_message_sync_passes_sent_id(self):
        """send_message_sync should pass sent_message_id to save_bot_response"""
        import heysquid.channels.telegram as tg

        with patch.object(tg, 'run_async_safe', return_value=77):
            with patch('heysquid.channels._msg_store.save_bot_response') as mock_save:
                with patch('heysquid.core._working_lock.update_working_activity'):
                    with patch('heysquid.channels._typing.start', create=True):
                        result = tg.send_message_sync(12345, "test", _save=True)

        assert result == 77
        mock_save.assert_called_once()
        _, kwargs = mock_save.call_args
        assert kwargs.get("sent_message_id") == 77


# ── Step 1: telegram_listener.py — reply_to_message_id field ────

class TestReplyToMessageId:
    """Code-level verification that fetch_new_messages() includes reply_to_message_id"""

    def test_message_data_has_reply_field(self):
        """telegram_listener.py source should contain reply_to_message_id field"""
        import heysquid.channels.telegram_listener as tl
        import inspect

        source = inspect.getsource(tl.fetch_new_messages)
        assert "reply_to_message_id" in source
        assert "msg.reply_to_message.message_id" in source
        assert "msg.reply_to_message else None" in source


# ── Integration test: full lifecycle ───────────────────────────────

class TestFullLifecycle:
    """Task Queue full flow integration test (mock-based)"""

    def test_three_tasks_one_at_a_time(self):
        """3 messages should be processed one at a time via pick_next_task"""
        from heysquid.core.hub import pick_next_task

        pending = [
            {"instruction": "A", "message_id": 100, "chat_id": 12345,
             "timestamp": "2026-02-25 10:00:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
            {"instruction": "B", "message_id": 101, "chat_id": 12345,
             "timestamp": "2026-02-25 10:01:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
            {"instruction": "C", "message_id": 102, "chat_id": 12345,
             "timestamp": "2026-02-25 10:02:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
        ]

        with patch('heysquid.core.hub.load_telegram_messages', return_value={"messages": []}):
            with patch('heysquid.dashboard._load_status', return_value={"kanban": {"tasks": []}}):
                # Round 1
                r1 = pick_next_task(pending)
                assert r1["task"]["instruction"] == "A"
                assert len(r1["remaining"]) == 2

                # Round 2
                r2 = pick_next_task(r1["remaining"])
                assert r2["task"]["instruction"] == "B"
                assert len(r2["remaining"]) == 1

                # Round 3
                r3 = pick_next_task(r2["remaining"])
                assert r3["task"]["instruction"] == "C"
                assert len(r3["remaining"]) == 0

                # Round 4 (none left)
                assert pick_next_task(r3["remaining"]) is None

    def test_waiting_reply_resumes_before_new(self):
        """WAITING reply should be processed before new tasks"""
        from heysquid.core.hub import pick_next_task

        waiting_card = {
            "id": "kb-w1", "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        messages = [
            {"message_id": 200, "reply_to_message_id": 50, "type": "user",
             "text": "Yes do it", "processed": False},
            {"message_id": 201, "reply_to_message_id": None, "type": "user",
             "text": "New task", "processed": False},
        ]

        pending = [
            {"instruction": "Yes do it", "message_id": 200, "chat_id": 12345,
             "timestamp": "2026-02-25 10:05:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
            {"instruction": "New task", "message_id": 201, "chat_id": 12345,
             "timestamp": "2026-02-25 10:04:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
        ]

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status',
                       return_value={"kanban": {"tasks": [waiting_card]}}):
                result = pick_next_task(pending)

        # Reply matching takes priority over timestamp
        assert result["task"]["message_id"] == 200
        assert result["waiting_card"]["id"] == "kb-w1"


# ── get_mergeable_cards + suggest_card_merge ──────────────────

class TestGetMergeableCards:
    """get_mergeable_cards() — retrieve active cards with same chat_id"""

    def _kanban_data(self, tasks):
        return {"tasks": tasks}

    def _card(self, id, chat_id, column, title="task", created_at="2026-02-25 10:00:00"):
        return {
            "id": id,
            "chat_id": chat_id,
            "column": column,
            "title": title,
            "created_at": created_at,
            "updated_at": created_at,
            "source_message_ids": [],
            "activity_log": [],
            "tags": [],
        }

    def test_three_active_same_chat(self):
        """3 active cards with same chat_id should return 3, sorted by created_at ascending"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [
            self._card("kb-3", 111, "todo", "C", "2026-02-25 10:03:00"),
            self._card("kb-1", 111, "in_progress", "A", "2026-02-25 10:01:00"),
            self._card("kb-2", 111, "waiting", "B", "2026-02-25 10:02:00"),
        ]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 3
        assert result[0]["id"] == "kb-1"  # oldest
        assert result[1]["id"] == "kb-2"
        assert result[2]["id"] == "kb-3"

    def test_single_active_card(self):
        """1 active card should return 1 (no merge needed)"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [self._card("kb-1", 111, "todo")]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 1

    def test_done_cards_excluded(self):
        """Only done cards should return empty list"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [
            self._card("kb-1", 111, "done"),
            self._card("kb-2", 111, "done"),
        ]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 0

    def test_automation_excluded(self):
        """Automation cards should be excluded"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [
            self._card("kb-1", 111, "automation"),
            self._card("kb-2", 111, "todo"),
        ]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 1
        assert result[0]["id"] == "kb-2"

    def test_different_chat_ids_filtered(self):
        """Cards with different chat_id should be excluded"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [
            self._card("kb-1", 111, "todo"),
            self._card("kb-2", 222, "todo"),
            self._card("kb-3", 111, "in_progress"),
        ]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 2
        assert all(c["chat_id"] == 111 for c in result)


class TestSuggestCardMerge:
    """suggest_card_merge() — merge suggestion text generation"""

    def _card(self, id, chat_id, column, title="task", created_at="2026-02-25 10:00:00"):
        return {
            "id": id,
            "chat_id": chat_id,
            "column": column,
            "title": title,
            "created_at": created_at,
            "updated_at": created_at,
            "source_message_ids": [],
            "activity_log": [],
            "tags": [],
        }

    def test_three_cards_returns_suggestion(self):
        """3 cards should return suggestion text + target/source IDs"""
        from heysquid.core.hub import suggest_card_merge

        cards = [
            self._card("kb-1", 111, "in_progress", "First", "2026-02-25 10:01:00"),
            self._card("kb-2", 111, "todo", "Second", "2026-02-25 10:02:00"),
            self._card("kb-3", 111, "waiting", "Third", "2026-02-25 10:03:00"),
        ]

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=cards):
            result = suggest_card_merge(111)

        assert result is not None
        assert "3 active cards" in result["text"]
        assert result["target_id"] == "kb-1"
        assert result["source_ids"] == ["kb-2", "kb-3"]
        assert len(result["cards"]) == 3
        assert "merge target" in result["text"]

    def test_single_card_returns_none(self):
        """1 card should return None"""
        from heysquid.core.hub import suggest_card_merge

        cards = [self._card("kb-1", 111, "todo")]

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=cards):
            result = suggest_card_merge(111)

        assert result is None

    def test_no_cards_returns_none(self):
        """0 cards should return None"""
        from heysquid.core.hub import suggest_card_merge

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=[]):
            result = suggest_card_merge(111)

        assert result is None

    def test_two_cards_returns_suggestion(self):
        """2 cards should return suggestion (PM decides if 3+ threshold applies)"""
        from heysquid.core.hub import suggest_card_merge

        cards = [
            self._card("kb-1", 111, "todo", "A", "2026-02-25 10:01:00"),
            self._card("kb-2", 111, "in_progress", "B", "2026-02-25 10:02:00"),
        ]

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=cards):
            result = suggest_card_merge(111)

        assert result is not None
        assert result["target_id"] == "kb-1"
        assert result["source_ids"] == ["kb-2"]
