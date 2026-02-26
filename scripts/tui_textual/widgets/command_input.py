"""CommandInput — Squad/Log 모드의 / 커맨드 입력 (Tab 자동완성)"""

from textual.widgets import Input
from textual.message import Message

COMMANDS = ["stop", "resume", "doctor", "skill", "merge", "done", "clean", "del", "move", "info", "squid", "kraken", "endsquad", "dashboard"]


class CommandInput(Input):
    """Squad/Log 모드에서 / 으로 시작하는 커맨드 입력"""

    DEFAULT_CSS = """
    CommandInput {
        dock: bottom;
        height: 1;
        margin: 0 1;
        display: none;
    }
    CommandInput.visible {
        display: block;
    }
    """

    class CommandSubmitted(Message):
        """커맨드 제출 이벤트"""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="/커맨드 입력... (Tab: 자동완성)",
            **kwargs,
        )
        self._tab_index = 0
        self._tab_candidates: list[str] = []  # 현재 cycling 대상

    def try_tab_complete(self) -> bool:
        """커맨드 자동완성. 성공하면 True."""
        text = self.value.strip()
        # 이미 완성된 커맨드(trailing space) → 기존 candidates에서 cycling
        if self.value.endswith(" ") and text.lower() in COMMANDS and self._tab_candidates:
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # 빈 입력 → 전체 목록
        if not text:
            self._tab_candidates = list(COMMANDS)
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # partial 입력 → 필터링
        candidates = [c for c in COMMANDS if c.startswith(text.lower())]
        if candidates:
            self._tab_candidates = candidates
            selected = candidates[self._tab_index % len(candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        return False

    def show(self) -> None:
        """커맨드 입력 표시"""
        self.add_class("visible")
        self.value = ""
        self._tab_index = 0
        self.focus()

    def hide(self) -> None:
        """커맨드 입력 숨기기"""
        self.remove_class("visible")
        self.value = ""
        self._tab_index = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 키 처리"""
        event.stop()
        text = self.value.strip()
        if text:
            self.post_message(CommandInput.CommandSubmitted(text))
        self.hide()

    def _on_key(self, event) -> None:
        """키 이벤트 — Escape 종료, Tab 자동완성"""
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.hide()
            return

        if event.key == "tab":
            if self.try_tab_complete():
                event.stop()
                event.prevent_default()
                return

        if event.key not in ("tab", "escape"):
            self._tab_index = 0
            self._tab_candidates = []
