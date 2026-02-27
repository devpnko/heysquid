"""AgentCompactBar -- Single-line compact agent status bar for Chat mode."""

from textual.widget import Widget
from textual.app import ComposeResult
from textual.widgets import Static

from heysquid.core.agents import AGENTS
from ..utils import AGENT_ORDER
from ..colors import AGENT_COLORS


class AgentCompactBar(Widget):
    """Compact single-line bar displaying agent statuses."""

    DEFAULT_CSS = """
    AgentCompactBar {
        height: 1;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("", id="agent-bar-content")

    def update_status(self, status: dict) -> None:
        """Update bar with agent status data."""
        parts = []
        for name in AGENT_ORDER:
            if name == "pm":
                continue
            info = AGENTS.get(name, {})
            emoji = info.get("emoji", "?")
            color = AGENT_COLORS.get(name, "#ffffff")
            agent_data = status.get(name, {})
            agent_st = agent_data.get("status", "idle")

            if agent_st == "idle":
                parts.append(f"[dim]{emoji}idle[/dim]")
            else:
                parts.append(f"[bold {color}]{emoji}{agent_st[:4]}[/bold {color}]")

        content = self.query_one("#agent-bar-content", Static)
        content.update("  ".join(parts))
