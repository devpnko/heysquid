"""LogView -- Mission Log + Stream Log widgets."""

from collections import deque

from textual.containers import VerticalScroll
from textual.widgets import Static

from heysquid.core.agents import AGENTS
from ..colors import AGENT_COLORS
from ..utils import trunc


class MissionLogView(VerticalScroll):
    """Mission Log -- Agent activity log (top section)."""

    DEFAULT_CSS = """
    MissionLogView {
        padding: 0 1;
    }
    MissionLogView > Static {
        width: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_snapshot = (0, None)

    def compose(self):
        yield Static("[bold]▸ MISSION[/bold]", classes="log-title")
        yield Static("", id="mission-log-content")

    def update_log(self, entries: list[dict]) -> None:
        """Update with mission_log entries."""
        snapshot = (len(entries), entries[-1] if entries else None)
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot

        parts = []
        for entry in entries:
            agent = entry.get("agent", "")
            t = entry.get("time", "")
            msg = entry.get("message", "")

            if agent == "commander":
                emoji = "🎖️"
                color = "#ffffff"
            elif agent == "system":
                emoji = "⚙️"
                color = "#888888"
            elif agent in AGENTS:
                emoji = AGENTS[agent].get("emoji", "🤖")
                color = AGENT_COLORS.get(agent, "#ffffff")
            else:
                emoji = "🔧"
                color = "#888888"

            parts.append(f"[{color}]\\[{t}] {emoji} {msg}[/{color}]")

        content = self.query_one("#mission-log-content", Static)
        content.update("\n".join(parts))

        self.call_after_refresh(self.scroll_end, animate=False)


class StreamLogView(VerticalScroll):
    """Stream Log -- Claude tool call log (bottom section, dimmed)."""

    DEFAULT_CSS = """
    StreamLogView {
        padding: 0 1;
    }
    StreamLogView > Static {
        width: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_snapshot = (0, None)

    def compose(self):
        yield Static("[bold dim]│ STREAM[/bold dim]", classes="log-title")
        yield Static("", id="stream-log-content")

    def update_log(self, buffer: deque) -> None:
        """Update with stream buffer."""
        snapshot = (len(buffer), buffer[-1] if buffer else None)
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot

        parts = []
        for tm, emoji, agent, text in buffer:
            color = AGENT_COLORS.get(agent, "#888888")
            if tm:
                parts.append(f"[dim][{color}]\\[{tm}] {emoji} {text}[/{color}][/dim]")
            else:
                parts.append(f"[dim][{color}]       {emoji} {text}[/{color}][/dim]")

        content = self.query_one("#stream-log-content", Static)
        content.update("\n".join(parts))

        self.call_after_refresh(self.scroll_end, animate=False)
