"""LogView — Mission Log + Stream Log 위젯"""

from collections import deque

from textual.containers import VerticalScroll
from textual.widgets import Static

from heysquid.core.agents import AGENTS
from ..colors import AGENT_COLORS
from ..utils import trunc


class MissionLogView(VerticalScroll):
    """Mission Log — 에이전트 활동 로그 (상단)"""

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
        self._last_count = 0

    def compose(self):
        yield Static("[bold]▸ MISSION[/bold]", classes="log-title")
        yield Static("", id="mission-log-content")

    def update_log(self, entries: list[dict]) -> None:
        """mission_log 엔트리 업데이트"""
        if len(entries) == self._last_count:
            return
        self._last_count = len(entries)

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
    """Stream Log — Claude 도구 호출 로그 (하단, dim)"""

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
        self._last_count = 0

    def compose(self):
        yield Static("[bold dim]│ STREAM[/bold dim]", classes="log-title")
        yield Static("", id="stream-log-content")

    def update_log(self, buffer: deque) -> None:
        """stream buffer 업데이트"""
        if len(buffer) == self._last_count:
            return
        self._last_count = len(buffer)

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
