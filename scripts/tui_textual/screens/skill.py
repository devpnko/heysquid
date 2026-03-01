"""SkillScreen -- Automation master-detail view (Ctrl+5 AUTO)."""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.tab_bar import TabBar
from ..widgets.auto_input import AutoInput
from ..widgets.auto_view import AutoMasterList, AutoDetailView
from ..data_poller import load_agent_status, load_fanmolt_agents, is_executor_live, get_executor_processes
from ..colors import AGENT_COLORS


class SkillScreen(Screen):
    """AUTO mode -- master-detail automation + FanMolt agent view."""

    DEFAULT_CSS = """
    SkillScreen {
        layout: vertical;
    }
    #skill-header {
        height: 1;
        padding: 0 1;
    }
    #skill-sep-top {
        height: 1;
    }
    #skill-body {
        height: 1fr;
    }
    #skill-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def __init__(self):
        super().__init__()
        self._level = 0  # 0=automations, 2=fanmolt agents
        self._skills: dict = {}  # cached automations data
        self._agents: list[dict] = []  # cached fanmolt agents
        self._drill_source = ""  # name of drilled automation

    def compose(self) -> ComposeResult:
        yield TabBar(active=4, id="skill-tab-bar")
        yield Static(self._header_text(), id="skill-header")
        yield AgentCompactBar()
        yield Static("\u2500" * 120, id="skill-sep-top")
        with Horizontal(id="skill-body"):
            yield AutoMasterList(id="auto-master")
            yield AutoDetailView(id="auto-detail")
        yield AutoInput(id="auto-cmd")
        yield Static(self._status_bar_text(), id="skill-status-bar")

    def on_mount(self) -> None:
        """Focus master list on mount."""
        try:
            self.query_one(AutoMasterList).focus()
        except Exception:
            pass

    def on_screen_resume(self) -> None:
        """Focus master list on screen switch."""
        try:
            self.query_one(AutoMasterList).focus()
        except Exception:
            pass

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        up = sum(1 for v in get_executor_processes().values() if v)
        if live:
            indicator = f"[bold green]\u25cf LIVE[/bold green] [dim]({up}/4)[/dim]"
        else:
            indicator = f"[dim]\u25cf STANDBY[/dim] [dim]({up}/4)[/dim]"
        return f"[bold]\U0001f991 SQUID[/bold]  [bold {pm_color}]\\[AUTOMATION][/bold {pm_color}]  {indicator}"

    def _status_bar_text(self) -> str:
        if self._level == 0:
            return "[dim] \u2191\u2193:nav  Enter:drill  r:run  t:toggle  Tab:input  q:quit  Ctrl+1~5:mode[/dim]"
        else:
            return "[dim] \u2191\u2193:nav  Esc:back  r:heartbeat  p:post  Tab:input  q:quit  Ctrl+1~5:mode[/dim]"

    def refresh_data(self, flash: str = "") -> None:
        """Refresh screen with polled data."""
        status = load_agent_status()

        try:
            header = self.query_one("#skill-header", Static)
            header.update(self._header_text())
        except Exception:
            pass

        try:
            bar = self.query_one(AgentCompactBar)
            bar.update_status(status)
        except Exception:
            pass

        self._skills = status.get("automations", {})

        if self._level == 0:
            try:
                master = self.query_one(AutoMasterList)
                master.update_automations(self._skills)
                # Update detail for current selection
                selected = master.get_selected()
                if selected:
                    name = selected["name"]
                    if name in self._skills:
                        detail = self.query_one(AutoDetailView)
                        detail.show_automation_detail(name, self._skills[name])
            except Exception:
                pass
        else:
            # Level 2: refresh agents
            self._agents = load_fanmolt_agents()
            try:
                master = self.query_one(AutoMasterList)
                master.update_agents(self._agents, self._drill_source)
                selected = master.get_selected()
                if selected:
                    handle = selected.get("handle", "")
                    agent = self._find_agent(handle)
                    if agent:
                        detail = self.query_one(AutoDetailView)
                        detail.show_agent_detail(handle, agent)
            except Exception:
                pass

        # Update status bar
        try:
            status_bar = self.query_one("#skill-status-bar", Static)
            if flash:
                status_bar.update(f"[dim] {flash}[/dim]")
            else:
                status_bar.update(self._status_bar_text())
        except Exception:
            pass

    def _find_agent(self, handle: str) -> dict | None:
        """Find agent by handle from cached agents list."""
        for a in self._agents:
            if a.get("handle") == handle:
                return a
        return None

    # --- Event handlers ---

    def on_auto_master_list_item_selected(self, event: AutoMasterList.ItemSelected) -> None:
        """Master list selection changed -> update detail panel."""
        try:
            detail = self.query_one(AutoDetailView)
            if event.level == 0:
                if event.name in self._skills:
                    detail.show_automation_detail(event.name, self._skills[event.name])
            else:
                agent = self._find_agent(event.name)
                if agent:
                    detail.show_agent_detail(event.name, agent)
        except Exception:
            pass

    def on_auto_master_list_drill_requested(self, event: AutoMasterList.DrillRequested) -> None:
        """Enter on drillable item -> switch to agent list."""
        self._level = 2
        self._drill_source = event.name
        self._agents = load_fanmolt_agents()
        try:
            master = self.query_one(AutoMasterList)
            master._selected_index = 0
            master.update_agents(self._agents, event.name)
            # Show first agent detail
            selected = master.get_selected()
            if selected:
                handle = selected.get("handle", "")
                agent = self._find_agent(handle)
                if agent:
                    detail = self.query_one(AutoDetailView)
                    detail.show_agent_detail(handle, agent)
            # Update status bar
            status_bar = self.query_one("#skill-status-bar", Static)
            status_bar.update(self._status_bar_text())
        except Exception:
            pass

    def on_auto_master_list_back_requested(self, event: AutoMasterList.BackRequested) -> None:
        """Esc at level 2 -> back to automations."""
        self._level = 0
        try:
            master = self.query_one(AutoMasterList)
            master._selected_index = 0
            master.update_automations(self._skills)
            # Show first automation detail
            selected = master.get_selected()
            if selected and selected["name"] in self._skills:
                detail = self.query_one(AutoDetailView)
                detail.show_automation_detail(selected["name"], self._skills[selected["name"]])
            status_bar = self.query_one("#skill-status-bar", Static)
            status_bar.update(self._status_bar_text())
        except Exception:
            pass

    def _on_key(self, event) -> None:
        """Handle shortcut keys r/t/p when input is not focused."""
        # Don't intercept if AutoInput is focused
        try:
            auto_input = self.query_one(AutoInput)
            if auto_input.has_focus:
                return
        except Exception:
            pass

        master = None
        try:
            master = self.query_one(AutoMasterList)
        except Exception:
            return

        selected = master.get_selected()
        if not selected:
            return

        if event.key == "r":
            event.stop()
            event.prevent_default()
            if self._level == 0:
                name = selected["name"]
                self._run_auto_command(f"run {name}")
            else:
                handle = selected.get("handle", selected.get("name", ""))
                self._run_auto_command(f"run {handle}")

        elif event.key == "t" and self._level == 0:
            event.stop()
            event.prevent_default()
            name = selected["name"]
            self._run_auto_command(f"toggle {name}")

        elif event.key == "p" and self._level == 2:
            event.stop()
            event.prevent_default()
            handle = selected.get("handle", selected.get("name", ""))
            self._run_auto_command(f"post {handle}")

        elif event.key == "tab":
            event.stop()
            event.prevent_default()
            try:
                self.query_one(AutoInput).focus()
            except Exception:
                pass

    def _run_auto_command(self, cmd: str) -> None:
        """Execute an auto command and show result as flash."""
        try:
            auto_input = self.query_one(AutoInput)
            auto_input.post_message(AutoInput.AutoCommandSubmitted(cmd))
        except Exception:
            pass
