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
        yield Static("[dim] q:quit  Ctrl+1/2/3/4:mode  Ctrl+\u2190\u2192  /cmd  drag+Ctrl+C:복사[/dim]", id="log-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = f"[bold green]● LIVE[/bold green]" if live else "[dim]○ IDLE[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[LOG][/bold {pm_color}]  {indicator}"

    def refresh_data(self, stream_buffer: deque, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신 — 각 섹션 독립적으로 보호"""
        # Stream Log 최우선 (가장 중요한 실시간 데이터)
        try:
            stream = self.query_one(StreamLogView)
            stream.update_log(stream_buffer)
        except Exception:
            pass

        # Mission Log (agent_status 의존)
        try:
            status = load_agent_status()
            mission = self.query_one(MissionLogView)
            mission.update_log(status.get("mission_log", []))
        except Exception:
            pass

        # 헤더
        try:
            header = self.query_one("#log-header", Static)
            header.update(self._header_text())
        except Exception:
            pass

        # 상태바
        if flash:
            try:
                status_bar = self.query_one("#log-status-bar", Static)
                status_bar.update(f"[dim] {flash}[/dim]")
            except Exception:
                pass
