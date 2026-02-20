"""SkillScreen — Skill 플러그인 상태 뷰"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import VerticalScroll

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.command_input import CommandInput
from ..data_poller import load_agent_status, is_executor_live
from ..colors import AGENT_COLORS


# 스킬 상태 아이콘
_STATUS_ICON = {
    "idle": "[dim]✓ idle[/dim]",
    "running": "[bold yellow]⏳ run[/bold yellow]",
    "error": "[bold red]✗ err[/bold red]",
    "disabled": "[dim]○ off[/dim]",
}


class SkillScreen(Screen):
    """Skill 모드 — 등록된 스킬 목록 + 상태"""

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
    #skill-table {
        height: 1fr;
        padding: 0 1;
    }
    #skill-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="skill-header")
        yield AgentCompactBar()
        yield Static("\u2500" * 120, id="skill-sep-top")
        yield VerticalScroll(Static("", id="skill-content"), id="skill-table")
        yield CommandInput(id="skill-cmd")
        yield Static(
            "[dim] q:quit  Ctrl+1/2/3/4:mode  Ctrl+\u2190\u2192  /cmd[/dim]",
            id="skill-status-bar",
        )

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = (
            "[bold green]\u25cf LIVE[/bold green]" if live else "[dim]\u25cb IDLE[/dim]"
        )
        return f"[bold]\U0001f991 SQUID[/bold]  [bold {pm_color}]\\[SKILL][/bold {pm_color}]  {indicator}"

    def refresh_data(self, flash: str = "") -> None:
        """폴링 데이터로 화면 갱신"""
        status = load_agent_status()

        # 헤더
        header = self.query_one("#skill-header", Static)
        header.update(self._header_text())

        # 에이전트 바
        bar = self.query_one(AgentCompactBar)
        bar.update_status(status)

        # 스킬 테이블
        skills = status.get("skills", {})
        content = self.query_one("#skill-content", Static)
        content.update(self._render_skills(skills))

        # 상태바
        if flash:
            status_bar = self.query_one("#skill-status-bar", Static)
            status_bar.update(f"[dim] {flash}[/dim]")

    def _render_skills(self, skills: dict) -> str:
        """스킬 데이터를 Rich 텍스트로 렌더링"""
        if not skills:
            return "[dim]등록된 스킬이 없습니다.[/dim]"

        # 헤더
        lines = []
        hdr = (
            f"  {'Name':<16} {'Status':<14} {'Trigger':<10} "
            f"{'Schedule':<10} {'Last Run':<20} {'Next Run':<20} "
            f"{'Workspace':<12} Description"
        )
        lines.append(f"[bold]{hdr}[/bold]")
        lines.append(f"  {'─' * 14}   {'─' * 12}   {'─' * 8}   {'─' * 8}   {'─' * 18}   {'─' * 18}   {'─' * 10}   {'─' * 20}")

        for name, skill in skills.items():
            enabled = skill.get("enabled", True)
            st = skill.get("status", "idle")
            if not enabled:
                st = "disabled"
            status_str = _STATUS_ICON.get(st, f"[dim]{st}[/dim]")

            trigger = skill.get("trigger", "manual")
            schedule = skill.get("schedule", "-")
            last_run = skill.get("last_run", "") or "-"
            next_run = skill.get("next_run", "") or "-"
            workspace = skill.get("workspace", "-") or "-"
            desc = skill.get("description", "")

            # next_run 포맷 정리 (ISO → 간결)
            if next_run != "-" and "T" in next_run:
                next_run = next_run.replace("T", " ")[:16]
            if last_run != "-" and "T" in last_run:
                last_run = last_run.replace("T", " ")[:16]

            line = (
                f"  {name:<16} {status_str:<14} {trigger:<10} "
                f"{schedule:<10} {last_run:<20} {next_run:<20} "
                f"{workspace:<12} [dim]{desc}[/dim]"
            )
            lines.append(line)

        # 요약
        total = len(skills)
        enabled_count = sum(1 for s in skills.values() if s.get("enabled", True))
        lines.append("")
        lines.append(f"  [dim]Total: {total}  |  Enabled: {enabled_count}[/dim]")

        return "\n".join(lines)
