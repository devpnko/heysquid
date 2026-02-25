"""Task Queue + WAITING State + Reply Matching 테스트

변경된 7개 파일 전체를 커버:
1. telegram_listener.py — reply_to_message_id 캡처
2. channels/telegram.py — sent_message_id 반환
3. _msg_store.py — sent_message_id 저장
4. dashboard/kanban.py — set_task_waiting + get_waiting_context
5. core/_working_lock.py — transition_to_waiting
6. core/hub.py — pick_next_task + ask_and_wait + 버그 수정
7. pm-workflow.md — 문서 (테스트 대상 아님)
"""

import json
import os
import time
import threading
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# ── 헬퍼: 격리된 _msg_store ────────────────────────────────────

def _make_store(tmp_data_dir):
    """격리된 환경에서 _msg_store 함수들을 반환"""
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
    """격리된 환경에서 kanban + dashboard 함수들을 반환"""
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

    # kanban도 동일한 함수를 사용하므로 패치 불필요 (dashboard.__init__에서 import)

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


# ── Step 3: _msg_store — sent_message_id 저장 ──────────────────

class TestSentMessageIdStore:
    """save_bot_response가 sent_message_id를 정상적으로 저장하는지 검증"""

    def test_save_with_sent_message_id(self, tmp_data_dir):
        """sent_message_id가 있을 때 저장되는지"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            ctx.save_bot_response(
                chat_id=12345, text="질문입니다",
                reply_to_message_ids=[100],
                channel="broadcast", sent_message_id=42
            )
            loaded = ctx.load()
            bot_msg = loaded["messages"][0]
            assert bot_msg["sent_message_id"] == 42
        finally:
            ctx.restore()

    def test_save_without_sent_message_id(self, tmp_data_dir):
        """sent_message_id가 None이면 필드가 없어야 함"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            ctx.save_bot_response(
                chat_id=12345, text="일반 응답",
                reply_to_message_ids=[100],
                channel="system"
            )
            loaded = ctx.load()
            bot_msg = loaded["messages"][0]
            assert "sent_message_id" not in bot_msg
        finally:
            ctx.restore()

    def test_backward_compat_no_sent_id_param(self, tmp_data_dir):
        """기존 호출 패턴 (sent_message_id 생략)이 작동하는지"""
        ctx = _make_store(tmp_data_dir)
        try:
            ctx.save({"messages": [], "last_update_id": 0})
            # 기존 코드처럼 sent_message_id 없이 호출
            ctx.save_bot_response(12345, "테스트", [200], None, "system")
            loaded = ctx.load()
            assert len(loaded["messages"]) == 1
            assert "sent_message_id" not in loaded["messages"][0]
        finally:
            ctx.restore()


# ── Step 4: kanban — WAITING 라이프사이클 ───────────────────────

class TestKanbanWaiting:
    """set_task_waiting + get_waiting_context 검증"""

    def test_set_task_waiting(self, tmp_data_dir):
        """IN_PROGRESS → WAITING 전환 + sent_ids 저장"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            task = ctx.add_task("Test task", "in_progress", [100], 12345)
            assert task is not None
            task_id = task["id"]

            result = ctx.set_task_waiting(task_id, [42, 43], "Waiting: 확인해주세요")
            assert result is True

            # 카드 상태 확인
            card = ctx.get_waiting_context(task_id)
            assert card is not None
            assert card["column"] == "waiting"
            assert card["waiting_sent_ids"] == [42, 43]
            assert "waiting_since" in card
            # activity_log 확인
            last_log = card["activity_log"][-1]
            assert "Waiting" in last_log["message"]
        finally:
            ctx.restore()

    def test_set_task_waiting_nonexistent(self, tmp_data_dir):
        """존재하지 않는 task_id → False"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            result = ctx.set_task_waiting("nonexistent-id", [42])
            assert result is False
        finally:
            ctx.restore()

    def test_get_waiting_context_returns_full_card(self, tmp_data_dir):
        """WAITING 카드의 전체 필드가 반환되는지"""
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
        """존재하지 않는 task → None"""
        ctx = _make_kanban(tmp_data_dir)
        try:
            result = ctx.get_waiting_context("nonexistent")
            assert result is None
        finally:
            ctx.restore()


# ── Step 5: _working_lock — transition_to_waiting ───────────────

class TestWorkingLockWaiting:
    """remove_working_lock(transition_to_waiting=True) 동작 검증"""

    def test_transition_to_waiting_removes_lock(self, tmp_data_dir):
        """transition_to_waiting=True여도 lock 파일은 삭제됨"""
        lock_file = str(tmp_data_dir / "working.json")

        import heysquid.core._working_lock as wl
        original = wl.WORKING_LOCK_FILE
        wl.WORKING_LOCK_FILE = lock_file

        try:
            # lock 파일 생성
            with open(lock_file, "w") as f:
                json.dump({"message_id": [100], "instruction_summary": "test"}, f)

            assert os.path.exists(lock_file)

            with patch.object(wl, '_dashboard_log'):
                with patch('heysquid.core._working_lock.set_pm_speech', create=True):
                    # typing stop을 mock
                    with patch('heysquid.channels._typing.stop', create=True):
                        wl.remove_working_lock(transition_to_waiting=True)

            assert not os.path.exists(lock_file)
        finally:
            wl.WORKING_LOCK_FILE = original

    def test_default_removes_lock_and_clears_speech(self, tmp_data_dir):
        """기본 호출 (transition_to_waiting=False)은 기존 동작 유지"""
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
            # set_pm_speech('') 호출 확인
            mock_speech.assert_called_with('')
        finally:
            wl.WORKING_LOCK_FILE = original


# ── Step 6: hub.py — 버그 수정 + pick_next_task + ask_and_wait ──

class TestBugFixInstructionKey:
    """check_telegram() 라인 403 버그 수정 — task.get('text') → task.get('instruction')"""

    def test_kanban_title_uses_instruction(self):
        """hub.py 소스에서 칸반 제목이 instruction 키를 사용하는지 확인.

        (task.get("instruction") or "New task")[:80] 패턴이 있어야 하고,
        (task.get("text") or "New task")[:80] 버그 패턴은 없어야 함.
        """
        import heysquid.core.hub as hub

        with open(hub.__file__) as f:
            source = f.read()

        # 수정된 패턴 존재 확인
        assert '(task.get("instruction") or "New task")' in source, \
            'task.get("instruction") or "New task" 패턴이 없음'
        # 버그 패턴 부재 확인
        assert '(task.get("text") or "New task")' not in source, \
            'task.get("text") or "New task" 버그가 여전히 존재'


class TestPickNextTask:
    """pick_next_task() — WAITING reply 매칭 + oldest TODO fallback"""

    def _make_pending(self, *ids_and_instructions):
        """테스트용 pending task 리스트 생성"""
        tasks = []
        for i, (mid, inst) in enumerate(ids_and_instructions):
            tasks.append({
                "instruction": inst,
                "message_id": mid,
                "chat_id": 12345,
                "timestamp": f"2026-02-25 10:{i:02d}:00",
                "context_24h": "",
                "user_name": "테스터",
                "files": [],
                "location": None,
                "stale_resume": False,
            })
        return tasks

    def test_single_task_returns_it(self):
        """pending 1개 → 그대로 반환"""
        from heysquid.core.hub import pick_next_task

        pending = self._make_pending((100, "A 해줘"))

        with patch('heysquid.core.hub.load_telegram_messages', return_value={"messages": []}):
            with patch('heysquid.dashboard._load_status', return_value={"kanban": {"tasks": []}}):
                result = pick_next_task(pending)

        assert result is not None
        assert result["task"]["message_id"] == 100
        assert result["waiting_card"] is None
        assert result["remaining"] == []

    def test_multiple_tasks_oldest_first(self):
        """pending 3개 → oldest(timestamp 순) 선택"""
        from heysquid.core.hub import pick_next_task

        pending = self._make_pending(
            (100, "A 해줘"),
            (101, "B 해줘"),
            (102, "C 해줘"),
        )

        with patch('heysquid.core.hub.load_telegram_messages', return_value={"messages": []}):
            with patch('heysquid.dashboard._load_status', return_value={"kanban": {"tasks": []}}):
                result = pick_next_task(pending)

        assert result["task"]["message_id"] == 100
        assert len(result["remaining"]) == 2

    def test_empty_returns_none(self):
        """빈 리스트 → None"""
        from heysquid.core.hub import pick_next_task
        assert pick_next_task([]) is None

    def test_waiting_reply_matched(self):
        """WAITING 카드의 sent_id에 reply_to_message_id 매칭"""
        from heysquid.core.hub import pick_next_task

        # WAITING 카드: sent_message_id=50으로 질문함
        waiting_card = {
            "id": "kb-waiting-1",
            "title": "A task",
            "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        # 메시지: msg_id=200이 msg_id=50에 대한 답장
        messages = [
            {"message_id": 200, "reply_to_message_id": 50, "type": "user",
             "text": "응 해줘", "processed": False},
            {"message_id": 201, "reply_to_message_id": None, "type": "user",
             "text": "B 해줘", "processed": False},
        ]

        pending = self._make_pending((200, "응 해줘"), (201, "B 해줘"))
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
        """WAITING 1개 + pending 1개 → 자동 매칭 (reply 없어도)"""
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
        """WAITING은 있지만 reply 매칭 안 되면 → oldest TODO"""
        from heysquid.core.hub import pick_next_task

        waiting_card = {
            "id": "kb-waiting-1",
            "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        # 2개 pending, 둘 다 reply 없음
        messages = [
            {"message_id": 400, "type": "user", "text": "X", "processed": False},
            {"message_id": 401, "type": "user", "text": "Y", "processed": False},
        ]

        pending = self._make_pending((400, "X 해줘"), (401, "Y 해줘"))
        kanban_data = {"kanban": {"tasks": [waiting_card]}}

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status', return_value=kanban_data):
                result = pick_next_task(pending)

        # WAITING 매칭 실패 → oldest
        assert result["task"]["message_id"] == 400
        assert result["waiting_card"] is None


class TestAskAndWait:
    """ask_and_wait() — 질문 전송 + WAITING 전환 + lock 해제"""

    def test_ask_and_wait_sends_and_transitions(self, tmp_data_dir):
        """정상 흐름: 전송 → 봇응답 저장 → WAITING → lock 해제"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=99) as mock_send:
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.dashboard.kanban.get_active_kanban_task_id', return_value="kb-123"):
                    with patch('heysquid.dashboard.kanban.set_task_waiting') as mock_waiting:
                        with patch('heysquid.core.hub.remove_working_lock') as mock_unlock:
                            result = ask_and_wait(12345, [100], "이렇게 할까요?")

        assert result is True

        # send_message_sync 호출 확인
        mock_send.assert_called_once_with(12345, "이렇게 할까요?", _save=False)

        # save_bot_response 호출 확인 (sent_message_id=99)
        mock_save.assert_called_once()
        call_kwargs = mock_save.call_args
        assert call_kwargs[1].get("sent_message_id") == 99 or call_kwargs[0][-1] == 99

        # set_task_waiting 호출 확인
        mock_waiting.assert_called_once_with("kb-123", [99], reason="Waiting: 이렇게 할까요?")

        # remove_working_lock(transition_to_waiting=True)
        mock_unlock.assert_called_once_with(transition_to_waiting=True)

    def test_ask_and_wait_send_failure(self):
        """전송 실패 → False 반환, 나머지 호출 안 됨"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=False):
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.core.hub.remove_working_lock') as mock_unlock:
                    result = ask_and_wait(12345, [100], "질문")

        assert result is False
        mock_save.assert_not_called()
        mock_unlock.assert_not_called()

    def test_ask_and_wait_single_message_id(self):
        """message_id가 int일 때도 정상 작동"""
        from heysquid.core.hub import ask_and_wait

        with patch('heysquid.channels.telegram.send_message_sync', return_value=88):
            with patch('heysquid.core.hub.save_bot_response') as mock_save:
                with patch('heysquid.dashboard.kanban.get_active_kanban_task_id', return_value=None):
                    with patch('heysquid.core.hub.remove_working_lock'):
                        result = ask_and_wait(12345, 100, "단일 ID 테스트")

        assert result is True
        # ids가 [100]으로 변환되어 전달
        assert mock_save.call_args[0][2] == [100]


# ── Step 2: telegram.py — send_message 반환값 ──────────────────

class TestSendMessageReturnValue:
    """send_message()가 int(msg_id)를 반환하는지 검증"""

    def test_send_message_returns_int(self):
        """정상 전송 시 int(message_id) 반환"""
        import heysquid.channels.telegram as tg
        import asyncio

        mock_msg = MagicMock()
        mock_msg.message_id = 42

        # async mock — send_message는 async 함수이므로 coroutine 반환 필요
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
        """int 반환값이 bool 체크와 호환되는지"""
        assert bool(42) is True   # int → truthy
        assert bool(0) is False   # 0은 아직 falsy이긴 하지만 message_id가 0일 일은 없음

    def test_send_message_sync_passes_sent_id(self):
        """send_message_sync가 sent_message_id를 save_bot_response에 전달하는지"""
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


# ── Step 1: telegram_listener.py — reply_to_message_id 필드 ────

class TestReplyToMessageId:
    """fetch_new_messages()가 reply_to_message_id를 포함하는지 코드 레벨 검증"""

    def test_message_data_has_reply_field(self):
        """telegram_listener.py 소스에 reply_to_message_id 필드가 있는지"""
        import heysquid.channels.telegram_listener as tl
        import inspect

        source = inspect.getsource(tl.fetch_new_messages)
        assert "reply_to_message_id" in source
        assert "msg.reply_to_message.message_id" in source
        assert "msg.reply_to_message else None" in source


# ── 통합 테스트: 전체 라이프사이클 ───────────────────────────────

class TestFullLifecycle:
    """Task Queue 전체 흐름 통합 테스트 (mock 기반)"""

    def test_three_tasks_one_at_a_time(self):
        """메시지 3개 → pick_next_task로 1개씩 처리"""
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
                # 1차
                r1 = pick_next_task(pending)
                assert r1["task"]["instruction"] == "A"
                assert len(r1["remaining"]) == 2

                # 2차
                r2 = pick_next_task(r1["remaining"])
                assert r2["task"]["instruction"] == "B"
                assert len(r2["remaining"]) == 1

                # 3차
                r3 = pick_next_task(r2["remaining"])
                assert r3["task"]["instruction"] == "C"
                assert len(r3["remaining"]) == 0

                # 4차 (없음)
                assert pick_next_task(r3["remaining"]) is None

    def test_waiting_reply_resumes_before_new(self):
        """WAITING 답장이 새 작업보다 우선 처리"""
        from heysquid.core.hub import pick_next_task

        waiting_card = {
            "id": "kb-w1", "column": "waiting",
            "source_message_ids": [100],
            "waiting_sent_ids": [50],
            "activity_log": [],
        }

        messages = [
            {"message_id": 200, "reply_to_message_id": 50, "type": "user",
             "text": "응 해줘", "processed": False},
            {"message_id": 201, "reply_to_message_id": None, "type": "user",
             "text": "새 작업", "processed": False},
        ]

        pending = [
            {"instruction": "응 해줘", "message_id": 200, "chat_id": 12345,
             "timestamp": "2026-02-25 10:05:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
            {"instruction": "새 작업", "message_id": 201, "chat_id": 12345,
             "timestamp": "2026-02-25 10:04:00", "context_24h": "", "user_name": "u",
             "files": [], "location": None, "stale_resume": False},
        ]

        with patch('heysquid.core.hub.load_telegram_messages',
                   return_value={"messages": messages}):
            with patch('heysquid.dashboard._load_status',
                       return_value={"kanban": {"tasks": [waiting_card]}}):
                result = pick_next_task(pending)

        # reply 매칭이 timestamp보다 우선
        assert result["task"]["message_id"] == 200
        assert result["waiting_card"]["id"] == "kb-w1"


# ── get_mergeable_cards + suggest_card_merge ──────────────────

class TestGetMergeableCards:
    """get_mergeable_cards() — 같은 chat_id의 활성 카드 조회"""

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
        """같은 chat_id 활성 카드 3개 → 3개 반환, created_at 오름차순"""
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
        """활성 카드 1개 → 1개 반환 (병합 불필요)"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [self._card("kb-1", 111, "todo")]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 1

    def test_done_cards_excluded(self):
        """done 카드만 → 빈 리스트"""
        from heysquid.dashboard.kanban import get_mergeable_cards

        tasks = [
            self._card("kb-1", 111, "done"),
            self._card("kb-2", 111, "done"),
        ]

        with patch('heysquid.dashboard._store.store.load', return_value=self._kanban_data(tasks)):
            result = get_mergeable_cards(111)

        assert len(result) == 0

    def test_automation_excluded(self):
        """automation 카드는 제외"""
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
        """다른 chat_id 카드는 제외"""
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
    """suggest_card_merge() — 병합 제안 텍스트 생성"""

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
        """카드 3개 → 제안 텍스트 + target/source IDs 반환"""
        from heysquid.core.hub import suggest_card_merge

        cards = [
            self._card("kb-1", 111, "in_progress", "First", "2026-02-25 10:01:00"),
            self._card("kb-2", 111, "todo", "Second", "2026-02-25 10:02:00"),
            self._card("kb-3", 111, "waiting", "Third", "2026-02-25 10:03:00"),
        ]

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=cards):
            result = suggest_card_merge(111)

        assert result is not None
        assert "3개" in result["text"]
        assert result["target_id"] == "kb-1"
        assert result["source_ids"] == ["kb-2", "kb-3"]
        assert len(result["cards"]) == 3
        assert "여기에 합침" in result["text"]

    def test_single_card_returns_none(self):
        """카드 1개 → None"""
        from heysquid.core.hub import suggest_card_merge

        cards = [self._card("kb-1", 111, "todo")]

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=cards):
            result = suggest_card_merge(111)

        assert result is None

    def test_no_cards_returns_none(self):
        """카드 0개 → None"""
        from heysquid.core.hub import suggest_card_merge

        with patch('heysquid.dashboard.kanban.get_mergeable_cards', return_value=[]):
            result = suggest_card_merge(111)

        assert result is None

    def test_two_cards_returns_suggestion(self):
        """카드 2개 → 제안 반환 (PM이 3개 이상에서만 제안할지는 PM 판단)"""
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
