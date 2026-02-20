"""SquadScreen — 에이전트 상태 + 토론 뷰"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal, Vertical, VerticalScroll

from heysquid.core.agents import AGENTS, KRAKEN_CREW

from ..widgets.agent_panel import AgentPanel
from ..widgets.squad_view import SquadDiscussionView
from ..widgets.command_input import CommandInput
from ..data_poller import load_agent_status, is_executor_live
from ..colors import AGENT_COLORS, ENTRY_TYPE_STYLE


class SquadScreen(Screen):
    """Squad 모드 — 왼쪽 에이전트 패널 + 오른쪽 토론 뷰"""

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
    #squad-discussion {
        width: 1fr;
    }
    #squad-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="squad-header")
        yield Static("", id="squad-subheader")
        yield Static("─" * 120, id="squad-sep")
        with Horizontal(id="squad-body"):
            yield AgentPanel(id="squad-agent-panel")
            yield SquadDiscussionView(id="squad-discussion")
        yield CommandInput(id="squad-cmd")
        yield Static("[dim] q:quit  Tab:mode  :cmd[/dim]", id="squad-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = f"[bold green]● LIVE[/bold green]" if live else "[dim]○ IDLE[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[SQUAD][/bold {pm_color}]  {indicator}"

    def refresh_data(self, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신"""
        status = load_agent_status()

        # 헤더
        header = self.query_one("#squad-header", Static)
        header.update(self._header_text())

        # 서브헤더: 토론 모드/주제
        squad = status.get("squad_log")
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

        # 에이전트 패널
        panel = self.query_one(AgentPanel)
        panel.update_status(status)

        # 토론 뷰
        discussion = self.query_one(SquadDiscussionView)
        discussion.update_squad(squad)

        # 상태바
        if flash:
            status_bar = self.query_one("#squad-status-bar", Static)
            status_bar.update(f"[dim] {flash}[/dim]")
