"""SquadDiscussionView — 스크롤 가능 토론 뷰"""

from textual.containers import VerticalScroll
from textual.widgets import Static

from heysquid.core.agents import AGENTS, KRAKEN_CREW
from ..utils import AGENT_SHORT
from ..colors import AGENT_COLORS, ENTRY_TYPE_STYLE

ENTRY_TYPE_LABELS = {
    "opinion": "의견",
    "agree": "동의",
    "disagree": "반대",
    "proposal": "제안",
    "conclusion": "결론",
    "risk": "리스크",
}


def _get_squad_agent_info(agent_key: str) -> tuple[str, str, str, bool]:
    """agent 키 → (emoji, display_name, color_hex, is_crew)"""
    if agent_key.startswith("kraken:"):
        expert_name = agent_key[7:]
        expert = KRAKEN_CREW.get(expert_name, {})
        emoji = expert.get("emoji", "🤖")
        role = expert.get("role", "Expert")
        display = f"{expert.get('name', expert_name)} ({role})"
        return emoji, display, "#888888", True
    elif agent_key in AGENTS:
        info = AGENTS[agent_key]
        emoji = info.get("emoji", "🤖")
        display = AGENT_SHORT.get(agent_key, agent_key)
        color = AGENT_COLORS.get(agent_key, "#ffffff")
        return emoji, display, color, False
    else:
        return "🤖", agent_key, "#ffffff", False


class SquadDiscussionView(VerticalScroll):
    """스크롤 가능한 토론 뷰"""

    DEFAULT_CSS = """
    SquadDiscussionView {
        padding: 0 1;
    }
    SquadDiscussionView > Static {
        width: 100%;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._last_entry_count = -1

    def compose(self):
        yield Static("[bold]DISCUSSION[/bold]", classes="disc-title")
        yield Static("", id="squad-disc-content")

    def update_squad(self, squad: dict | None) -> None:
        """토론 데이터로 뷰 업데이트"""
        if not squad:
            content = self.query_one("#squad-disc-content", Static)
            content.update(
                "[dim]토론이 없습니다.\n\n"
                ":squid @agent1 @agent2 주제\n"
                "  → Squid 모드 토론 시작\n\n"
                ":kraken \\[주제]\n"
                "  → Kraken 모드 (전원+Crew)[/dim]"
            )
            self._last_entry_count = -1
            return

        entries = squad.get("entries", [])
        entry_count = len(entries)
        if entry_count == self._last_entry_count:
            return
        self._last_entry_count = entry_count

        status_label = squad.get("status", "active")
        if status_label == "active":
            header = "[bold]DISCUSSION[/bold]  [bold green]● ACTIVE[/bold green]"
        else:
            header = "[bold]DISCUSSION[/bold]  [dim]○ CONCLUDED[/dim]"

        # Kraken 참가자 아이콘
        parts = [header]
        if squad.get("mode") == "kraken":
            icons = ""
            for p in squad.get("participants", []):
                icons += AGENTS.get(p, {}).get("emoji", "")
            for ve in squad.get("virtual_experts", []):
                icons += KRAKEN_CREW.get(ve, {}).get("emoji", "")
            if icons:
                parts.append(f"[dim]{icons}[/dim]")

        parts.append("")

        # 엔트리 렌더링
        for entry in entries:
            agent_key = entry.get("agent", "")
            etype = entry.get("type", "opinion")
            msg = entry.get("message", "")
            etime = entry.get("time", "")

            emoji, display, color, is_crew = _get_squad_agent_info(agent_key)
            type_label = ENTRY_TYPE_LABELS.get(etype, etype)
            type_emoji, _ = ENTRY_TYPE_STYLE.get(etype, ("💬", "#ffffff"))

            if is_crew:
                parts.append(f"[dim]{etime} {emoji} {display} [{type_label}][/dim]")
                if msg:
                    parts.append(f"[dim]  {msg}[/dim]")
            else:
                parts.append(f"[{color}]{etime} {emoji} {display}[/{color}] {type_emoji} [{type_label}]")
                if msg:
                    parts.append(f"  {msg}")
            parts.append("")

        # 업데이트
        title = self.query_one(".disc-title", Static)
        title.update(header)
        content = self.query_one("#squad-disc-content", Static)
        content.update("\n".join(parts))

        # 자동 스크롤
        self.call_after_refresh(self.scroll_end, animate=False)
