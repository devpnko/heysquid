"""AgentPanel -- Left-side agent status panel for Squad mode."""

from textual.containers import VerticalScroll
from textual.widgets import Static

from heysquid.core.agents import AGENTS
from ..utils import AGENT_ORDER, AGENT_SHORT, trunc
from ..colors import AGENT_COLORS


class AgentPanel(VerticalScroll):
    """Agent status panel (Squad mode, left side)."""

    DEFAULT_CSS = """
    AgentPanel {
        padding: 1 0;
    }
    AgentPanel > Static {
        width: 100%;
    }
    """

    def compose(self):
        yield Static("[bold]AGENTS[/bold]", classes="panel-title")
        yield Static("", id="agent-panel-content")

    def update_status(self, status: dict) -> None:
        """Update agent statuses."""
        parts = []
        for name in AGENT_ORDER:
            info = AGENTS.get(name, {})
            emoji = info.get("emoji", "?")
            color = AGENT_COLORS.get(name, "#ffffff")
            short = AGENT_SHORT.get(name, name[:3])

            agent_data = status.get(name, {})
            agent_st = agent_data.get("status", "idle")
            task = agent_data.get("task", "")

            parts.append(f"[bold {color}]{emoji} {short}[/bold {color}]")
            if agent_st == "idle":
                parts.append("  [dim]idle[/dim]")
            else:
                task_str = trunc(task, 14) if task else agent_st
                parts.append(f"  [green]▶ {task_str}[/green]")
            parts.append("")  # spacing

        content = self.query_one("#agent-panel-content", Static)
        content.update("\n".join(parts))
