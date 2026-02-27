"""KanbanScreen — 칸반 보드 뷰 (가로 5컬럼)"""

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
    """터미널 셀 폭 계산 (한글=2cell)"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in text)


def _trunc(text: str, max_cells: int) -> str:
    """터미널 셀 폭 기준으로 텍스트 자르기 (한글=2cell)"""
    width = 0
    for i, ch in enumerate(text):
        w = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if width + w > max_cells:
            return text[:i]
        width += w
    return text


def _wrap_lines(text: str, max_cells: int, max_lines: int = 2) -> list[str]:
    """텍스트를 셀 폭 기준으로 여러 줄로 나누기 (한글=2cell)."""
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
        # 마지막 줄 말줄임
        last = lines[-1]
        trimmed = _trunc(last, max_cells - 1)
        lines[-1] = trimmed + "\u2026"
    return lines

# 컬럼 정의: (key, short_label, color_hex)
_COLUMNS = [
    ("automation", "Auto", "#cc66ff"),
    ("todo", "Todo", "#00d4ff"),
    ("in_progress", "Prog", "#ff9f43"),
    ("waiting", "Wait", "#ffd32a"),
    ("done", "Done", "#26de81"),
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
            "[dim] done K1 | move K1 ip | del K1 | info K1 | merge K1 K2 | clean   Tab:\uc644\uc131  q:quit  ^1~5:mode[/dim]",
            id="kanban-status-bar",
        )

    def on_screen_resume(self) -> None:
        """화면 전환 시 입력창에 자동 포커스"""
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
        """info 패널에 카드 상세 정보 표시"""
        try:
            panel = self.query_one("#kanban-info-panel")
            content = self.query_one("#kanban-info-content", Static)
            content.update(text)
            panel.styles.display = "block"
        except Exception:
            pass

    def hide_info(self) -> None:
        """info 패널 숨기기"""
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

    def _render_columns(self, status: dict) -> None:
        """각 컬럼 위젯에 데이터 렌더링"""
        kanban = status.get("kanban", {})
        tasks = kanban.get("tasks", [])
        skills = status.get("automations", {})

        # 컬럼별 카드 텍스트 수집
        groups: dict[str, list[str]] = {key: [] for key, _, _ in _COLUMNS}

        # 글로벌 카드 번호 (모든 카드에 K-ID 부여)
        card_num = 0

        # Automations — 카드 스타일
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
            short_name = _trunc(name, 10)
            lines = [
                f"[{bc_auto}]\u256d\u2500[/{bc_auto}]",
                f"[{bc_auto}]\u2502[/{bc_auto}] [bold cyan]{sid}[/bold cyan] {icon} [bold]{short_name}[/bold]",
                f"[{bc_auto}]\u2502[/{bc_auto}] [dim]{sched_s} runs:{runs}[/dim]",
                f"[{bc_auto}]\u2570\u2500[/{bc_auto}]",
            ]
            groups["automation"].append("\n".join(lines))

        # Task cards — 카드 스타일
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

            # ID + 아이콘 접두어 폭 계산 후 제목 줄바꿈
            id_label = f"[bold cyan]{sid}[/bold cyan] " if sid else ""
            prefix_icon = "[dim]\u2713[/dim] " if col == "done" else ""
            # ID(ex: "K1 ")=4cells + 아이콘("✓ ")=2cells → 첫줄은 좁고 둘째줄은 넓음
            id_cells = _cell_width(sid) + 1 if sid else 0  # +1 for space
            icon_cells = 2 if col == "done" else 0
            first_line_max = 14 - id_cells - icon_cells
            cont_line_max = 14

            title_lines = _wrap_lines(raw_title, first_line_max, max_lines=1)
            if _cell_width(raw_title) > first_line_max:
                # 첫 줄에 안 담기면 2줄로 분배
                title_lines = _wrap_lines(raw_title, cont_line_max, max_lines=2)
                lines.append(f"[{bc}]\u2502[/{bc}] {id_label}{prefix_icon}{title_lines[0]}")
                for tl in title_lines[1:]:
                    lines.append(f"[{bc}]\u2502[/{bc}]  {tl}")
            else:
                lines.append(f"[{bc}]\u2502[/{bc}] {id_label}{prefix_icon}{title_lines[0]}")

            # 메타 정보
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
                meta.append("[#ffd32a]\u23f3\ub300\uae30[/#ffd32a]")
            if meta:
                lines.append(f"[{bc}]\u2502[/{bc}]  [dim]{' '.join(meta)}[/dim]")
            else:
                lines.append(f"[{bc}]\u2502[/{bc}]  [dim]\u2500[/dim]")

            lines.append(f"[{bc}]\u2570\u2500[/{bc}]")
            groups[col].append("\n".join(lines))

        # 각 컬럼 위젯 업데이트
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
