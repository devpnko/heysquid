"""SquadScreen -- Agent status + history/discussion split view."""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal, Vertical

from heysquid.core.agents import AGENTS, KRAKEN_CREW

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.agent_panel import AgentPanel
from ..widgets.tab_bar import TabBar
from ..widgets.squad_view import SquadHistoryList, SquadEntryView
from ..widgets.command_input import CommandInput
from ..data_poller import load_agent_status, load_squad_history, is_executor_live, get_executor_processes
from ..colors import AGENT_COLORS


class SquadScreen(Screen):
    """Squad mode -- left agent panel + right history/discussion split."""

    DEFAULT_CSS = """
    SquadScreen {
        layout: vertical;
    }
    #squad-header {
        height: 1;
        padding: 0 1;
    }
    #squad-subheader {
        height: 1;
        padding: 0 1;
    }
    #squad-sep {
        height: 1;
    }
    #squad-body {
        height: 1fr;
    }
    #squad-agent-panel {
        width: 20;
        border-right: solid $surface;
    }
    #squad-right {
        width: 1fr;
    }
    #squad-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._selected_history_id: str | None = None  # None = active discussion

    def compose(self) -> ComposeResult:
        yield TabBar(active=2, id="squad-tab-bar")
        yield Static(self._header_text(), id="squad-header")
        yield AgentCompactBar()
        yield Static("", id="squad-subheader")
        yield Static("─" * 120, id="squad-sep")
        with Horizontal(id="squad-body"):
            yield AgentPanel(id="squad-agent-panel")
            with Vertical(id="squad-right"):
                yield SquadHistoryList(id="squad-history-list")
                yield SquadEntryView(id="squad-entry-view")
        yield CommandInput(id="squad-cmd")
        yield Static("[dim] q:quit  Ctrl+1~5:mode  /cmd  ↑↓:select  Enter:view  drag+Ctrl+C:copy[/dim]", id="squad-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        up = sum(1 for v in get_executor_processes().values() if v)
        if live:
            indicator = f"[bold green]● LIVE[/bold green] [dim]({up}/4)[/dim]"
        else:
            indicator = f"[bold red]● OFFLINE[/bold red] [dim]({up}/4)[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[SQUAD][/bold {pm_color}]  {indicator}"

    def refresh_data(self, flash: str = "") -> None:
        """Refresh screen with polled data -- each section protected independently."""
        status = load_agent_status()
        history = load_squad_history()

        # Header
        try:
            header = self.query_one("#squad-header", Static)
            header.update(self._header_text())
        except Exception:
            pass

        # Agent compact bar
        try:
            bar = self.query_one(AgentCompactBar)
            bar.update_status(status)
        except Exception:
            pass

        # Subheader + agent panel
        squad = status.get("squad_log")
        try:
            subheader = self.query_one("#squad-subheader", Static)
            if squad:
                mode_str = squad.get("mode", "squid")
                topic = squad.get("topic", "")
                if mode_str == "kraken":
                    subheader.update(f"[bold {AGENT_COLORS['pm']}]── 🦑 Kraken Mode ──[/bold {AGENT_COLORS['pm']}]  [dim]{topic}[/dim]")
                else:
                    subheader.update(f"[bold {AGENT_COLORS['pm']}]── 🦑 Squid Mode ──[/bold {AGENT_COLORS['pm']}]  [dim]{topic}[/dim]")
            else:
                subheader.update("")
        except Exception:
            pass

        try:
            panel = self.query_one(AgentPanel)
            panel.update_status(status)
        except Exception:
            pass

        # History + discussion view
        try:
            hist_list = self.query_one(SquadHistoryList)
            hist_list.update_history(history, squad)
        except Exception:
            pass

        try:
            entry_view = self.query_one(SquadEntryView)
            if self._selected_history_id is not None:
                selected = None
                for item in history:
                    if item.get("id") == self._selected_history_id:
                        selected = item
                        break
                entry_view.update_squad(selected)
            else:
                entry_view.update_squad(squad)
        except Exception:
            pass

        # Status bar
        if flash:
            try:
                status_bar = self.query_one("#squad-status-bar", Static)
                status_bar.update(f"[dim] {flash}[/dim]")
            except Exception:
                pass

    def on_squad_history_list_discussion_selected(
        self, event: SquadHistoryList.DiscussionSelected
    ) -> None:
        """Handle discussion selection from history list."""
        self._selected_history_id = event.discussion_id
        # Immediately refresh bottom view with selected discussion
        status = load_agent_status()
        history = load_squad_history()
        entry_view = self.query_one(SquadEntryView)

        if event.discussion_id is not None:
            selected = None
            for item in history:
                if item.get("id") == event.discussion_id:
                    selected = item
                    break
            entry_view._last_entry_count = -1  # force refresh
            entry_view.update_squad(selected)
        else:
            # Return to active discussion
            squad = status.get("squad_log")
            entry_view._last_entry_count = -1
            entry_view.update_squad(squad)
