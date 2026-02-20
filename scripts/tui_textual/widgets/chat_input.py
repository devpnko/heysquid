"""ChatInput — 채팅 입력 위젯 (TextArea 기반, 멀티라인, @멘션, 슬래시 커맨드)"""

from textual.widgets import TextArea
from textual.message import Message

from ..utils import get_at_context, AGENT_ORDER
from .command_input import COMMANDS


class ChatInput(TextArea):
    """Chat 모드 메시지 입력. TextArea 서브클래스.

    - Enter → 전송
    - Shift+Enter → 줄바꿈
    - Escape → 입력 클리어
    - Tab → /슬래시 커맨드 또는 @멘션 자동완성
    """

    DEFAULT_CSS = """
    ChatInput {
        height: 5;
        margin: 0 1;
    }
    """

    class ChatSubmitted(Message):
        """채팅 메시지 제출 이벤트"""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs):
        super().__init__(
            language=None,
            show_line_numbers=False,
            tab_behavior="focus",
            **kwargs,
        )
        self._tab_index = 0
        self._tab_candidates: list[str] = []

    def try_tab_complete(self) -> bool:
        """슬래시 커맨드 또는 @멘션 자동완성. 성공하면 True 반환."""
        text = self.text

        # --- 슬래시 커맨드 자동완성 ---
        if text.startswith("/"):
            partial = text.lstrip("/").rstrip(" ").lower()

            # 이미 완성된 커맨드(trailing space) → 기존 candidates에서 cycling
            if text.endswith(" ") and partial in COMMANDS and self._tab_candidates:
                selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            # "/" 만 입력 → 전체 목록
            if not partial:
                self._tab_candidates = list(COMMANDS)
                selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            # partial 입력 → 필터링
            candidates = [c for c in COMMANDS if c.startswith(partial)]
            if candidates:
                self._tab_candidates = candidates
                selected = candidates[self._tab_index % len(candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            return False

        # --- @멘션 자동완성 ---
        at_ctx = get_at_context(text)
        if at_ctx:
            prefix, partial, candidates = at_ctx
            if candidates:
                selected = candidates[self._tab_index % len(candidates)]
                self.text = prefix + "@" + selected + " "
                self._tab_index += 1
                return True
        return False

    def _on_key(self, event) -> None:
        """키 이벤트 처리"""
        if event.key == "enter":
            # Enter → 전송
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(ChatInput.ChatSubmitted(text))
            self.text = ""
            self._tab_index = 0
            self._tab_candidates = []
            return

        if event.key == "shift+enter":
            # Shift+Enter → 줄바꿈 (기본 동작)
            self._tab_index = 0
            self._tab_candidates = []
            super()._on_key(event)
            return

        if event.key == "escape":
            if self.text:
                event.stop()
                event.prevent_default()
                self.text = ""
                self._tab_index = 0
                self._tab_candidates = []
                return

        if event.key == "tab":
            if self.try_tab_complete():
                event.stop()
                event.prevent_default()
                return

        if event.key not in ("tab", "escape"):
            self._tab_index = 0
            self._tab_candidates = []
