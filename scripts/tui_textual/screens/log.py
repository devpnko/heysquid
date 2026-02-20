"""LogScreen — Mission Log + Stream Log 통합 뷰"""

from collections import deque

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll

from heysquid.core.agents import AGENTS

from ..widgets.log_view import MissionLogView, StreamLogView
from ..widgets.command_input import CommandInput
from ..data_poller import load_agent_status, is_executor_live
from ..colors import AGENT_COLORS


class LogScreen(Screen):
    """Log 모드 — Mission Log (상) + Stream Log (하) 반반 분할"""

    DEFAULT_CSS = """
    LogScreen {
        layout: vertical;
    }
    #log-header {
        height: 1;
        padding: 0 1;
    }
    #log-sep-top {
        height: 1;
    }
    #log-mission {
        height: 1fr;
        border-bottom: solid $surface;
    }
    #log-stream {
        height: 1fr;
    }
    #log-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="log-header")
        yield Static("─" * 120, id="log-sep-top")
        yield MissionLogView(id="log-mission")
        yield StreamLogView(id="log-stream")
        yield CommandInput(id="log-cmd")
        yield Static("[dim] q:quit  Ctrl+1/2/3/4:mode  Ctrl+\u2190\u2192  /cmd[/dim]", id="log-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = f"[bold green]● LIVE[/bold green]" if live else "[dim]○ IDLE[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[LOG][/bold {pm_color}]  {indicator}"

    def refresh_data(self, stream_buffer: deque, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신"""
        status = load_agent_status()

        # 헤더
        header = self.query_one("#log-header", Static)
        header.update(self._header_text())

        # Mission Log
        mission = self.query_one(MissionLogView)
        mission.update_log(status.get("mission_log", []))

        # Stream Log
        stream = self.query_one(StreamLogView)
        stream.update_log(stream_buffer)

        # 상태바
        if flash:
            status_bar = self.query_one("#log-status-bar", Static)
            status_bar.update(f"[dim] {flash}[/dim]")
