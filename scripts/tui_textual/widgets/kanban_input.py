"""KanbanInput — 칸반 전용 커맨드 입력 (항상 표시, / 불필요)"""

from textual.widgets import Input
from textual.message import Message

# 칸반에서 사용 가능한 명령어만
KANBAN_COMMANDS = ["done", "move", "del", "info", "merge", "clean"]


class KanbanInput(Input):
    """칸반 화면 하단 고정 입력. done K1, move K1 ip 형태로 바로 입력."""

    DEFAULT_CSS = """
    KanbanInput {
        dock: bottom;
        height: 1;
        margin: 0 1;
    }
    """

    class KanbanCommandSubmitted(Message):
        """칸반 커맨드 제출 이벤트"""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="done K1 | move K1 ip | del K1 | info K1 | merge K1 K2 | clean",
            **kwargs,
        )
        self._tab_index = 0
        self._tab_candidates: list[str] = []

    def try_tab_complete(self) -> bool:
        """칸반 커맨드 자동완성."""
        text = self.value.strip()
        # 이미 완성된 커맨드 → cycling
        if self.value.endswith(" ") and text.lower() in KANBAN_COMMANDS and self._tab_candidates:
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # 빈 입력 → 전체 목록
        if not text:
            self._tab_candidates = list(KANBAN_COMMANDS)
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # partial → 필터링
        candidates = [c for c in KANBAN_COMMANDS if c.startswith(text.lower())]
        if candidates:
            self._tab_candidates = candidates
            selected = candidates[self._tab_index % len(candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        return False

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 키 처리"""
        event.stop()
        text = self.value.strip()
        if text:
            self.post_message(KanbanInput.KanbanCommandSubmitted(text))
        self.value = ""

    def _on_key(self, event) -> None:
        """Tab 자동완성"""
        if event.key == "tab":
            if self.try_tab_complete():
                event.stop()
                event.prevent_default()
                return
        if event.key not in ("tab",):
            self._tab_index = 0
            self._tab_candidates = []
