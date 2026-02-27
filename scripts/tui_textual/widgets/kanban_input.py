"""KanbanInput -- Kanban-specific command input (always visible, no / prefix needed)."""

from textual.binding import Binding
from textual.widgets import Input
from textual.message import Message

# Only commands available in kanban mode
KANBAN_COMMANDS = ["done", "move", "del", "info", "merge", "clean"]


class KanbanInput(Input):
    """Fixed input at bottom of kanban screen. Direct input like: done K1, move K1 ip."""

    DEFAULT_CSS = """
    KanbanInput {
        height: auto;
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("tab", "tab_complete", "Tab Complete", show=False),
    ]

    class KanbanCommandSubmitted(Message):
        """Kanban command submitted event."""
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

    def action_tab_complete(self) -> None:
        """Tab key -> kanban command autocomplete."""
        text = self.value.strip()
        # Already completed command -> cycle
        if self.value.endswith(" ") and text.lower() in KANBAN_COMMANDS and self._tab_candidates:
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return
        # Empty input -> show full list
        if not text:
            self._tab_candidates = list(KANBAN_COMMANDS)
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return
        # Partial -> filter
        candidates = [c for c in KANBAN_COMMANDS if c.startswith(text.lower())]
        if candidates:
            self._tab_candidates = candidates
            selected = candidates[self._tab_index % len(candidates)]
            self.value = selected + " "
            self._tab_index += 1

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key."""
        event.stop()
        text = self.value.strip()
        if text:
            self.post_message(KanbanInput.KanbanCommandSubmitted(text))
        self.value = ""

    def on_input_changed(self, event: Input.Changed) -> None:
        """Reset tab state on input change."""
        self._tab_index = 0
        self._tab_candidates = []
