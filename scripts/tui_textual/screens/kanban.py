"""KanbanScreen — 칸반 보드 뷰 (가로 5컬럼, 읽기 전용)"""

from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal, VerticalScroll

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.tab_bar import TabBar
from ..widgets.kanban_input import KanbanInput
from ..data_poller import load_agent_status, is_executor_live
from ..colors import AGENT_COLORS

# 컬럼 정의: (key, short_label, color_hex)
_COLUMNS = [
    ("automation", "⚙️Auto", "#cc66ff"),
    ("todo", "📥Todo", "#00d4ff"),
    ("in_progress", "⚡Prog", "#ff9f43"),
    ("waiting", "⏳Wait", "#ffd32a"),
    ("done", "✅Done", "#26de81"),
]


class KanbanScreen(Screen):
    """Kanban 모드 — MISSION BOARD (가로 5컬럼)"""

    DEFAULT_CSS = """
    KanbanScreen {
        layout: vertical;
    }
    #kanban-header {
        height: 1;
        padding: 0 1;
    }
    #kanban-sep-top {
        height: 1;
    }
    #kanban-board {
        height: 1fr;
    }
    .kanban-col {
        width: 1fr;
        height: 100%;
        border-right: solid dimgray;
    }
    .kanban-col:last-child {
        border-right: none;
    }
    .kanban-col-header {
        height: 1;
        padding: 0 1;
        text-align: center;
    }
    .kanban-col-body {
        height: 1fr;
        padding: 0;
    }
    #kanban-status-bar {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TabBar(active=1, id="kanban-tab-bar")
        yield Static(self._header_text(), id="kanban-header")
        yield AgentCompactBar()
        yield Static("\u2500" * 200, id="kanban-sep-top")
        with Horizontal(id="kanban-board"):
            for key, label, color in _COLUMNS:
                with VerticalScroll(classes="kanban-col", id=f"kcol-{key}"):
                    yield Static(f"[bold {color}]{label} (0)[/bold {color}]", classes="kanban-col-header", id=f"khead-{key}")
                    yield Static("", classes="kanban-col-body", id=f"kbody-{key}")
        yield KanbanInput(id="kanban-cmd")
        yield Static(
            "[dim] q:quit  Ctrl+1~5:mode  Tab:자동완성  Ctrl+C:복사[/dim]",
            id="kanban-status-bar",
        )

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        indicator = (
            "[bold green]\u25cf LIVE[/bold green]" if live else "[dim]\u25cb IDLE[/dim]"
        )
        return f"[bold]\U0001f991 SQUID[/bold]  [bold {pm_color}]\\[KANBAN][/bold {pm_color}]  {indicator}"

    def refresh_data(self, flash: str = "") -> None:
        status = load_agent_status()

        try:
            header = self.query_one("#kanban-header", Static)
            header.update(self._header_text())
        except Exception:
            pass

        try:
            bar = self.query_one(AgentCompactBar)
            bar.update_status(status)
        except Exception:
            pass

        try:
            self._render_columns(status)
        except Exception:
            pass

        if flash:
            try:
                status_bar = self.query_one("#kanban-status-bar", Static)
                status_bar.update(f"[dim] {flash}[/dim]")
            except Exception:
                pass

    def _render_columns(self, status: dict) -> None:
        """각 컬럼 위젯에 데이터 렌더링"""
        kanban = status.get("kanban", {})
        tasks = kanban.get("tasks", [])
        skills = status.get("automations", {})

        # 컬럼별 카드 텍스트 수집
        groups: dict[str, list[str]] = {key: [] for key, _, _ in _COLUMNS}

        # Automations — 카드 스타일
        for name, sk in skills.items():
            if not sk.get("enabled", True):
                continue
            st = sk.get("status", "idle")
            icon = {"idle": "[dim]✓[/dim]", "running": "[yellow]⏳[/yellow]", "error": "[red]✗[/red]"}.get(st, st)
            sched = sk.get("schedule", "")
            sched_s = f" {sched}" if sched else ""
            runs = sk.get("run_count", 0)
            card = f"[#cc66ff]╭─[/#cc66ff]\n"
            card += f"[#cc66ff]│[/#cc66ff] {icon} [bold]{name}[/bold]{sched_s}\n"
            card += f"[#cc66ff]│[/#cc66ff] [dim]runs:{runs}[/dim]\n"
            card += f"[#cc66ff]╰─[/#cc66ff]"
            groups["automation"].append(card)

        # Task cards — 카드 스타일
        col_border = {
            "todo": "#00d4ff",
            "in_progress": "#ff9f43",
            "waiting": "#ffd32a",
            "done": "#26de81",
        }
        card_num = 0
        for task in tasks:
            col = task.get("column", "todo")
            if col not in groups:
                continue
            bc = col_border.get(col, "#555555")
            title = task.get("title", "")[:26]
            tags = task.get("tags", [])
            tag_s = " ".join(f"[dim]#{t}[/dim]" for t in tags[:2]) if tags else ""
            updated = task.get("updated_at") or ""
            time_s = updated.split(" ")[1][:5] if " " in updated else ""
            logs_n = len(task.get("activity_log", []))
            result = task.get("result")

            lines = [f"[{bc}]╭─[/{bc}]"]

            # ID + title
            if col not in ("done", "automation"):
                sid = task.get("short_id", f"#{card_num + 1}")
                card_num += 1
                lines.append(f"[{bc}]│[/{bc}] [bold cyan]{sid}[/bold cyan] {title}")
            else:
                lines.append(f"[{bc}]│[/{bc}] [dim]✓[/dim] {title}")

            # tags
            if tag_s:
                lines.append(f"[{bc}]│[/{bc}]  {tag_s}")

            # meta
            meta = []
            if time_s:
                meta.append(time_s)
            if logs_n:
                meta.append(f"{logs_n}log")
            if result:
                meta.append("[green]✓[/green]")
            if meta:
                lines.append(f"[{bc}]│[/{bc}]  [dim]{' '.join(meta)}[/dim]")

            # progress bar for in_progress
            if col == "in_progress":
                lines.append(f"[{bc}]│[/{bc}]  [{bc}]▰▰▰▰▰▱▱▱[/{bc}]")

            # waiting label
            if col == "waiting":
                lines.append(f"[{bc}]│[/{bc}]  [#ffd32a]⏳ 대기 중[/#ffd32a]")

            lines.append(f"[{bc}]╰─[/{bc}]")
            groups[col].append("\n".join(lines))

        # 각 컬럼 위젯 업데이트
        for key, label, color in _COLUMNS:
            items = groups[key]
            count = len(items)

            # 헤더 업데이트
            try:
                head = self.query_one(f"#khead-{key}", Static)
                head.update(f"[bold {color}]{label} ({count})[/bold {color}]")
            except Exception:
                pass

            # 바디 업데이트
            try:
                body = self.query_one(f"#kbody-{key}", Static)
                if items:
                    body.update("\n".join(items))
                else:
                    body.update("[dim](empty)[/dim]")
            except Exception:
                pass
