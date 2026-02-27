"""TabBar -- Top mode tab bar (CHAT ^1 | KANBAN ^2 | ...)."""

from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static

TABS = [
    ("CHAT", "^1"),
    ("KANBAN", "^2"),
    ("SQUAD", "^3"),
    ("LOG", "^4"),
    ("AUTO", "^5"),
]

# Active tab color
TAB_ACTIVE_COLOR = "#ff6b9d"


class TabBar(Widget):
    """Mode switching tab bar -- highlights the currently active mode."""

    DEFAULT_CSS = """
    TabBar {
        height: 1;
        background: #12122a;
    }
    """

    def __init__(self, active: int = 0, **kwargs):
        super().__init__(**kwargs)
        self._active = active

    def compose(self) -> ComposeResult:
        yield Static(self._build_tabs(), id="tab-bar-content")

    def set_active(self, index: int) -> None:
        """Change active tab."""
        self._active = index
        try:
            content = self.query_one("#tab-bar-content", Static)
            content.update(self._build_tabs())
        except Exception:
            pass

    def _build_tabs(self) -> str:
        parts = []
        for i, (name, shortcut) in enumerate(TABS):
            if i == self._active:
                parts.append(
                    f"[bold {TAB_ACTIVE_COLOR}] {name} [/bold {TAB_ACTIVE_COLOR}]"
                    f"[dim]{shortcut}[/dim]"
                )
            else:
                parts.append(f"[dim] {name} {shortcut}[/dim]")
        return " │ ".join(parts)
