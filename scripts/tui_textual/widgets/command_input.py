"""CommandInput -- Slash command input for Squad/Log modes (Tab autocomplete)."""

from textual.widgets import Input
from textual.message import Message

COMMANDS = ["stop", "resume", "doctor", "skill", "merge", "done", "clean", "del", "move", "info", "squid", "kraken", "endsquad", "dashboard"]


class CommandInput(Input):
    """Slash command input for Squad/Log modes."""

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
        """Command submitted event."""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs):
        super().__init__(
            placeholder="/command... (Tab: autocomplete)",
            **kwargs,
        )
        self._tab_index = 0
        self._tab_candidates: list[str] = []  # current cycling candidates

    def try_tab_complete(self) -> bool:
        """Autocomplete command. Returns True on success."""
        text = self.value.strip()
        # Already completed command (trailing space) -> cycle through candidates
        if self.value.endswith(" ") and text.lower() in COMMANDS and self._tab_candidates:
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # Empty input -> show full list
        if not text:
            self._tab_candidates = list(COMMANDS)
            selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        # Partial input -> filter
        candidates = [c for c in COMMANDS if c.startswith(text.lower())]
        if candidates:
            self._tab_candidates = candidates
            selected = candidates[self._tab_index % len(candidates)]
            self.value = selected + " "
            self._tab_index += 1
            return True
        return False

    def show(self) -> None:
        """Show command input."""
        self.add_class("visible")
        self.value = ""
        self._tab_index = 0
        self.focus()

    def hide(self) -> None:
        """Hide command input."""
        self.remove_class("visible")
        self.value = ""
        self._tab_index = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key."""
        event.stop()
        text = self.value.strip()
        if text:
            self.post_message(CommandInput.CommandSubmitted(text))
        self.hide()

    def _on_key(self, event) -> None:
        """Key events -- Escape to close, Tab to autocomplete."""
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
