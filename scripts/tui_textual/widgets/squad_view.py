"""SquadView — 히스토리 목록 + 토론 엔트리 뷰"""

from textual.containers import VerticalScroll
from textual.widgets import Static, ListView, ListItem
from textual.message import Message

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


def _render_entries(entries: list[dict]) -> str:
    """토론 엔트리를 Rich 마크업 문자열로 렌더링"""
    parts = []
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
    return "\n".join(parts)


class SquadHistoryList(VerticalScroll):
    """상단 히스토리 목록"""

    class DiscussionSelected(Message):
        """히스토리 항목 선택"""
        def __init__(self, discussion_id: str | None) -> None:
            super().__init__()
            self.discussion_id = discussion_id

    DEFAULT_CSS = """
    SquadHistoryList {
        height: 8;
        border-bottom: solid $surface;
        padding: 0 1;
    }
    SquadHistoryList > Static {
        width: 100%;
    }
    .hist-item {
        height: 1;
    }
    .hist-item-selected {
        height: 1;
        background: $surface;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items: list[dict] = []  # history items
        self._active: dict | None = None
        self._selected_index = 0
        self._last_render_key = ""

    def compose(self):
        yield Static("", id="squad-hist-content")

    def update_history(self, history: list[dict], active_squad: dict | None) -> None:
        """히스토리 + 활성 토론으로 목록 갱신"""
        self._items = history
        self._active = active_squad

        # 변경 감지: active 상태 + 히스토리 수 + active entries 수
        active_entries = len(active_squad.get("entries", [])) if active_squad else 0
        render_key = f"{len(history)}:{active_squad is not None}:{active_entries}"
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key

        lines = []
        total_items = []

        # Active 토론 (맨 위)
        if active_squad:
            mode = active_squad.get("mode", "squid")
            mode_icon = "🐙" if mode == "kraken" else "🦑"
            topic = active_squad.get("topic", "")
            n_entries = len(active_squad.get("entries", []))
            status = active_squad.get("status", "active")
            if status == "active":
                lines.append(f"[bold green]● {mode_icon} {topic} — {n_entries} entries[/bold green]")
            else:
                lines.append(f"[bold yellow]○ {mode_icon} {topic} — {n_entries} entries (concluded)[/bold yellow]")
            total_items.append({"type": "active", "data": active_squad})

        # 아카이브된 히스토리 (최신순)
        for item in reversed(history):
            mode = item.get("mode", "squid")
            mode_icon = "🐙" if mode == "kraken" else "🦑"
            topic = item.get("topic", "")
            n_entries = len(item.get("entries", []))
            date = item.get("archived_at", "")[:10]
            lines.append(f"[dim]  {mode_icon} {topic} ({date}) — {n_entries} entries[/dim]")
            total_items.append({"type": "history", "data": item})

        if not lines:
            lines.append("[dim]토론 기록이 없습니다[/dim]")

        content = self.query_one("#squad-hist-content", Static)
        content.update("\n".join(lines))

    def _on_key(self, event) -> None:
        """키보드: Up/Down 선택, Enter로 하단 뷰에 표시"""
        all_items = []
        if self._active:
            all_items.append({"type": "active", "data": self._active})
        for item in reversed(self._items):
            all_items.append({"type": "history", "data": item})

        if not all_items:
            return

        if event.key == "up":
            event.stop()
            event.prevent_default()
            self._selected_index = max(0, self._selected_index - 1)
            self._highlight_and_select(all_items)
        elif event.key == "down":
            event.stop()
            event.prevent_default()
            self._selected_index = min(len(all_items) - 1, self._selected_index + 1)
            self._highlight_and_select(all_items)
        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            if 0 <= self._selected_index < len(all_items):
                item = all_items[self._selected_index]
                disc_id = item["data"].get("id") if item["type"] == "history" else None
                self.post_message(SquadHistoryList.DiscussionSelected(disc_id))

    def _highlight_and_select(self, all_items):
        """선택된 항목 하이라이트 + 하단 뷰에 표시"""
        lines = []
        for i, item in enumerate(all_items):
            data = item["data"]
            mode = data.get("mode", "squid")
            mode_icon = "🐙" if mode == "kraken" else "🦑"
            topic = data.get("topic", "")
            n_entries = len(data.get("entries", []))
            prefix = "▸ " if i == self._selected_index else "  "

            if item["type"] == "active":
                status = data.get("status", "active")
                if status == "active":
                    if i == self._selected_index:
                        lines.append(f"[bold green on $surface]{prefix}● {mode_icon} {topic} — {n_entries} entries[/bold green on $surface]")
                    else:
                        lines.append(f"[bold green]{prefix}● {mode_icon} {topic} — {n_entries} entries[/bold green]")
                else:
                    lines.append(f"[bold yellow]{prefix}○ {mode_icon} {topic} — {n_entries} entries (concluded)[/bold yellow]")
            else:
                date = data.get("archived_at", "")[:10]
                if i == self._selected_index:
                    lines.append(f"[on $surface]{prefix}{mode_icon} {topic} ({date}) — {n_entries} entries[/on $surface]")
                else:
                    lines.append(f"[dim]{prefix}{mode_icon} {topic} ({date}) — {n_entries} entries[/dim]")

        content = self.query_one("#squad-hist-content", Static)
        content.update("\n".join(lines))

        # 선택된 토론의 entries를 하단에 표시
        if 0 <= self._selected_index < len(all_items):
            item = all_items[self._selected_index]
            disc_id = item["data"].get("id") if item["type"] == "history" else None
            self.post_message(SquadHistoryList.DiscussionSelected(disc_id))


class SquadEntryView(VerticalScroll):
    """하단 토론 엔트리 뷰 (스크롤 가능)"""

    DEFAULT_CSS = """
    SquadEntryView {
        padding: 0 1;
    }
    SquadEntryView > Static {
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
        elif status_label == "concluded":
            header = "[bold]DISCUSSION[/bold]  [dim]○ CONCLUDED[/dim]"
        else:
            header = "[bold]DISCUSSION[/bold]  [dim]○ ARCHIVED[/dim]"

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
        parts.append(_render_entries(entries))

        # 업데이트
        title = self.query_one(".disc-title", Static)
        title.update(header)
        content = self.query_one("#squad-disc-content", Static)
        content.update("\n".join(parts))

        # 자동 스크롤 (active일 때만)
        if status_label == "active":
            self.call_after_refresh(self.scroll_end, animate=False)


# Backward compatibility alias
SquadDiscussionView = SquadEntryView
