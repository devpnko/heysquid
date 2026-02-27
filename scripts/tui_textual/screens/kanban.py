"""KanbanScreen -- Kanban board view (horizontal 5 columns)."""

import unicodedata
from textual.screen import Screen
from textual.app import ComposeResult
from textual.widgets import Static
from textual.containers import Horizontal, Vertical, VerticalScroll

from ..widgets.agent_bar import AgentCompactBar
from ..widgets.tab_bar import TabBar
from ..widgets.kanban_input import KanbanInput
from ..data_poller import load_agent_status, is_executor_live, get_executor_processes
from ..colors import AGENT_COLORS


def _cell_width(text: str) -> int:
    """Calculate terminal cell width (CJK=2 cells)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _trunc(text: str, max_cells: int) -> str:
    """Truncate text by terminal cell width (CJK=2 cells)."""
    width = 0
    for i, ch in enumerate(text):
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > max_cells:
            return text[:i]
        width += w
    return text


def _wrap_lines(text: str, max_cells: int, max_lines: int = 2) -> list[str]:
    """Split text into multiple lines by cell width (CJK=2 cells)."""
    lines = []
    remaining = text
    for _ in range(max_lines):
        if not remaining:
            break
        width = 0
        cut = len(remaining)
        for i, ch in enumerate(remaining):
            w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
            if width + w > max_cells:
                cut = i
                break
            width += w
        lines.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining and lines:
        # Ellipsis on last line
        last = lines[-1]
        trimmed = _trunc(last, max_cells - 1)
        lines[-1] = trimmed + "\u2026"
    return lines

# Column definitions: (key, short_label, color_hex)
_COLUMNS = [
    ("automation", "Auto", "#cc66ff"),
    ("todo", "Todo", "#00d4ff"),
    ("in_progress", "Prog", "#ff9f43"),
    ("waiting", "Wait", "#ffd32a"),
    ("done", "Done", "#26de81"),
]


class KanbanScreen(Screen):
    """Kanban mode -- MISSION BOARD (horizontal 5 columns)."""

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
    }
    .kanban-col-header {
        height: 1;
        padding: 0 1;
        text-align: center;
        background: #12122a;
    }
    .kanban-col-body {
        padding: 0 1;
    }
    #kanban-info-panel {
        height: auto;
        max-height: 8;
        padding: 0 1;
        background: #12122a;
        border-top: solid #2a2a50;
        display: none;
    }
    #kanban-status-bar {
        height: 1;
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
                with Vertical(classes="kanban-col", id=f"kcol-{key}"):
                    yield Static(
                        f"[bold {color}]{label} (0)[/bold {color}]",
                        classes="kanban-col-header",
                        id=f"khead-{key}",
                    )
                    yield VerticalScroll(
                        Static("", id=f"kbody-{key}"),
                        classes="kanban-col-body",
                        can_focus=False,
                    )
        yield VerticalScroll(
            Static("", id="kanban-info-content"),
            id="kanban-info-panel",
            can_focus=False,
        )
        yield KanbanInput(id="kanban-cmd")
        yield Static(
            "[dim] done K1 | move K1 ip | del K1 | info K1 | merge K1 K2 | clean   Tab:complete  q:quit  ^1~5:mode[/dim]",
            id="kanban-status-bar",
        )

    def on_screen_resume(self) -> None:
        """Auto-focus input on screen switch."""
        try:
            self.query_one(KanbanInput).focus()
        except Exception:
            pass

    def _header_text(self) -> str:
        pm_color = AGENT_COLORS.get("pm", "#ff6b9d")
        live = is_executor_live()
        up = sum(1 for v in get_executor_processes().values() if v)
        if live:
            indicator = f"[bold green]\u25cf LIVE[/bold green] [dim]({up}/4)[/dim]"
        else:
            indicator = f"[bold red]\u25cf OFFLINE[/bold red] [dim]({up}/4)[/dim]"
        return f"[bold]\U0001f991 SQUID[/bold]  [bold {pm_color}]\\[KANBAN][/bold {pm_color}]  {indicator}"

    def show_info(self, text: str) -> None:
        """Show card details in info panel."""
        try:
            panel = self.query_one("#kanban-info-panel")
            content = self.query_one("#kanban-info-content", Static)
            content.update(text)
            panel.styles.display = "block"
        except Exception:
            pass

    def hide_info(self) -> None:
        """Hide info panel."""
        try:
            panel = self.query_one("#kanban-info-panel")
            panel.styles.display = "none"
        except Exception:
            pass

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

    def _get_card_width(self) -> int:
        """Calculate card text width from column body widget's actual content width."""
        try:
            # VerticalScroll (kanban-col-body) content area width
            body_scroll = self.query_one("#kbody-todo").parent
            # content_region = actual content area excluding padding/scrollbar
            w = body_scroll.content_region.width
            # Card border chars = 2 cells excluded
            return max(w - 2, 8)
        except Exception:
            return 14

    def _render_columns(self, status: dict) -> None:
        """Render data into each column widget."""
        kanban = status.get("kanban", {})
        tasks = kanban.get("tasks", [])
        skills = status.get("automations", {})

        card_w = self._get_card_width()

        # Collect card text per column
        groups: dict[str, list[str]] = {key: [] for key, _, _ in _COLUMNS}

        # Global card number (K-ID assigned to all cards)
        card_num = 0

        # Automations -- card style
        bc_auto = "#cc66ff"
        for name, sk in skills.items():
            if not sk.get("enabled", True):
                continue
            card_num += 1
            sid = f"A{card_num}"
            st = sk.get("status", "idle")
            icon = {"idle": "[dim]\u2713[/dim]", "running": "[yellow]\u23f3[/yellow]", "error": "[red]\u2717[/red]"}.get(st, st)
            sched = sk.get("schedule", "")
            sched_s = f" {sched}" if sched else ""
            runs = sk.get("run_count", 0)
            short_name = _trunc(name, card_w - 6)  # exclude sid+icon space
            lines = [
                f"[{bc_auto}]\u256d\u2500[/{bc_auto}]",
                f"[{bc_auto}]\u2502[/{bc_auto}] [bold cyan]{sid}[/bold cyan] {icon} [bold]{short_name}[/bold]",
                f"[{bc_auto}]\u2502[/{bc_auto}] [dim]{sched_s} runs:{runs}[/dim]",
                f"[{bc_auto}]\u2570\u2500[/{bc_auto}]",
            ]
            groups["automation"].append("\n".join(lines))

        # Task cards -- card style
        col_border = {
            "todo": "#00d4ff",
            "in_progress": "#ff9f43",
            "waiting": "#ffd32a",
            "done": "#26de81",
        }
        for task in tasks:
            col = task.get("column", "todo")
            if col not in groups:
                continue
            bc = col_border.get(col, "#555555")
            sid = task.get("short_id", "")
            raw_title = task.get("title", "")
            updated = task.get("updated_at") or ""
            time_s = updated.split(" ")[1][:5] if " " in updated else ""
            logs_n = len(task.get("activity_log", []))
            result = task.get("result")

            lines = [f"[{bc}]\u256d\u2500[/{bc}]"]

            # Calculate ID + icon prefix width, then wrap title
            id_label = f"[bold cyan]{sid}[/bold cyan] " if sid else ""
            prefix_icon = "[dim]\u2713[/dim] " if col == "done" else ""
            id_cells = _cell_width(sid) + 1 if sid else 0  # +1 for space
            icon_cells = 2 if col == "done" else 0
            first_line_max = card_w - id_cells - icon_cells
            cont_line_max = card_w - 1  # 1 cell indent

            title_lines = _wrap_lines(raw_title, first_line_max, max_lines=1)
            if _cell_width(raw_title) > first_line_max:
                # If first line can't fit, distribute across 2 lines
                title_lines = _wrap_lines(raw_title, cont_line_max, max_lines=2)
                lines.append(f"[{bc}]\u2502[/{bc}] {id_label}{prefix_icon}{title_lines[0]}")
                for tl in title_lines[1:]:
                    lines.append(f"[{bc}]\u2502[/{bc}]  {tl}")
            else:
                lines.append(f"[{bc}]\u2502[/{bc}] {id_label}{prefix_icon}{title_lines[0]}")

            # Meta info
            meta = []
            if time_s:
                meta.append(time_s)
            if logs_n:
                meta.append(f"{logs_n}log")
            if result:
                meta.append("[green]\u2713[/green]")
            if col == "in_progress":
                meta.append(f"[{bc}]\u25b0\u25b0\u25b0\u25b1\u25b1[/{bc}]")
            if col == "waiting":
                meta.append("[#ffd32a]\u23f3wait[/#ffd32a]")
            if meta:
                lines.append(f"[{bc}]\u2502[/{bc}]  [dim]{' '.join(meta)}[/dim]")
            else:
                lines.append(f"[{bc}]\u2502[/{bc}]  [dim]\u2500[/dim]")

            lines.append(f"[{bc}]\u2570\u2500[/{bc}]")
            groups[col].append("\n".join(lines))

        # Update each column widget
        for key, label, color in _COLUMNS:
            items = groups[key]
            count = len(items)

            try:
                head = self.query_one(f"#khead-{key}", Static)
                head.update(f"[bold {color}]{label} ({count})[/bold {color}]")
            except Exception:
                pass

            try:
                body = self.query_one(f"#kbody-{key}", Static)
                if items:
                    body.update("\n".join(items))
                else:
                    body.update("[dim](empty)[/dim]")
            except Exception:
                pass
