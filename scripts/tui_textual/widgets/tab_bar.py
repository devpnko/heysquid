"""TabBar — 상단 모드 탭 바 (CHAT ^1 | KANBAN ^2 | ...)"""

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

# 활성 탭 컬러
TAB_ACTIVE_COLOR = "#ff6b9d"


class TabBar(Widget):
    """모드 전환 탭 바 — 현재 활성 모드를 하이라이트."""

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
        yield Static(self._render(), id="tab-bar-content")

    def set_active(self, index: int) -> None:
        """활성 탭 변경."""
        self._active = index
        try:
            content = self.query_one("#tab-bar-content", Static)
            content.update(self._render())
        except Exception:
            pass

    def _render(self) -> str:
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
