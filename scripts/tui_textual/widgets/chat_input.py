"""ChatInput -- Chat input widget (TextArea-based, multiline, @mention, slash commands)."""

from textual.widgets import TextArea
from textual.message import Message

from ..utils import get_at_context, AGENT_ORDER
from .command_input import COMMANDS


class ChatInput(TextArea):
    """Chat mode message input. TextArea subclass.

    - Enter -> send
    - Shift+Enter -> newline
    - Escape -> clear input
    - Tab -> /slash command or @mention autocomplete
    """

    DEFAULT_CSS = """
    ChatInput {
        height: 5;
        margin: 0 1;
    }
    """

    class ChatSubmitted(Message):
        """Chat message submitted event."""
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
        """Autocomplete slash command or @mention. Returns True on success."""
        text = self.text

        # --- Slash command autocomplete ---
        if text.startswith("/"):
            partial = text.lstrip("/").rstrip(" ").lower()

            # Already completed command (trailing space) -> cycle through candidates
            if text.endswith(" ") and partial in COMMANDS and self._tab_candidates:
                selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            # Only "/" entered -> show full list
            if not partial:
                self._tab_candidates = list(COMMANDS)
                selected = self._tab_candidates[self._tab_index % len(self._tab_candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            # Partial input -> filter
            candidates = [c for c in COMMANDS if c.startswith(partial)]
            if candidates:
                self._tab_candidates = candidates
                selected = candidates[self._tab_index % len(candidates)]
                self.text = "/" + selected + " "
                self._tab_index += 1
                return True

            return False

        # --- @mention autocomplete ---
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
        """Handle key events."""
        if event.key == "enter":
            # Enter -> send
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
            # Shift+Enter -> newline (default behavior)
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
