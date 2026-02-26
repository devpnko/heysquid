"""LogScreen — Mission Log + Stream Log 통합 뷰"""

from collections import deque

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Vertical, VerticalScroll

from heysquid.core.agents import AGENTS

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.log_view import MissionLogView, StreamLogView
from ..widgets.tab_bar import TabBar
from ..widgets.command_input import CommandInput
from ..data_poller import load_agent_status, is_executor_live, get_executor_processes
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
    #log-process-bar {
        height: 1;
        padding: 0 1;
        background: #0a0a1a;
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
        yield TabBar(active=3, id="log-tab-bar")
        yield Static(self._header_text(), id="log-header")
        yield AgentCompactBar()
        yield Static(self._process_status_text(), id="log-process-bar")
        yield Static("─" * 120, id="log-sep-top")
        yield MissionLogView(id="log-mission")
        yield StreamLogView(id="log-stream")
        yield CommandInput(id="log-cmd")
        yield Static("[dim] q:quit  Ctrl+1~5:mode  Ctrl+\u2190\u2192  /cmd  drag+Ctrl+C:복사[/dim]", id="log-status-bar")

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        up = sum(1 for v in get_executor_processes().values() if v)
        if live:
            indicator = f"[bold green]● LIVE[/bold green] [dim]({up}/4)[/dim]"
        else:
            indicator = f"[bold red]● OFFLINE[/bold red] [dim]({up}/4)[/dim]"
        return f"[bold]🦑 SQUID[/bold]  [bold {pm_color}]\\[LOG][/bold {pm_color}]  {indicator}"

    def _process_status_text(self) -> str:
        procs = get_executor_processes()
        parts = []
        labels = [
            ("executor", "executor"),
            ("claude", "claude PM"),
            ("caffeinate", "caffeinate"),
            ("viewer", "viewer"),
        ]
        up = 0
        for key, label in labels:
            alive = procs.get(key, False)
            if alive:
                parts.append(f"[green]●[/green] {label}")
                up += 1
            else:
                parts.append(f"[red]●[/red] [dim]{label}[/dim]")
        status = "  ".join(parts)
        count_color = "green" if up == 4 else "yellow" if up > 0 else "red"
        return f"{status}    [{count_color}]({up}/4)[/{count_color}]"

    def refresh_data(self, stream_buffer: deque, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신 — 각 섹션 독립적으로 보호"""
        status = load_agent_status()

        # Stream Log 최우선 (가장 중요한 실시간 데이터)
        try:
            stream = self.query_one(StreamLogView)
            stream.update_log(stream_buffer)
        except Exception:
            pass

        # Mission Log
        try:
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

        # 프로세스 상태 바
        try:
            proc_bar = self.query_one("#log-process-bar", Static)
            proc_bar.update(self._process_status_text())
        except Exception:
            pass

        # Agent 바
        try:
            bar = self.query_one(AgentCompactBar)
            bar.update_status(status)
        except Exception:
            pass

        # 상태바
        if flash:
            try:
                status_bar = self.query_one("#log-status-bar", Static)
                status_bar.update(f"[dim] {flash}[/dim]")
            except Exception:
                pass
