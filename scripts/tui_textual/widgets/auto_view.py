"""AutoView -- Master list + detail panel for AUTO (Ctrl+5) screen."""

from textual.widgets import Static
from textual.message import Message


# Status icons
_STATUS_ICON = {
    "idle": "✓",
    "running": "[bold yellow]⏳[/bold yellow]",
    "error": "[bold red]✗[/bold red]",
    "disabled": "[dim]○[/dim]",
}


class AutoMasterList(Static, can_focus=True):
    """Left master list -- automations (level 0) or FanMolt agents (level 2)."""

    class ItemSelected(Message):
        """An item was selected (cursor moved)."""
        def __init__(self, name: str, level: int) -> None:
            super().__init__()
            self.name = name
            self.level = level

    class DrillRequested(Message):
        """Enter pressed on fanmolt -> drill into agents."""
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class BackRequested(Message):
        """Esc pressed at level 2 -> back to level 0."""
        pass

    DEFAULT_CSS = """
    AutoMasterList {
        width: 34;
        border-right: solid $surface;
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._level = 0  # 0=automations, 2=agents
        self._selected_index = 0
        self._items: list[dict] = []  # [{name, status, enabled, ...}]
        self._last_render_key = ""
        self._drill_source = ""  # which automation was drilled into

    def update_automations(self, skills: dict) -> None:
        """Update with automation list (level 0)."""
        self._level = 0
        items = []
        for name, data in skills.items():
            items.append({
                "name": name,
                "enabled": data.get("enabled", True),
                "status": data.get("status", "idle"),
                "drillable": name.startswith("fanmolt"),
            })
        self._items = items
        if self._selected_index >= len(items):
            self._selected_index = max(0, len(items) - 1)
        self._refresh_list()

    def update_agents(self, agents: list[dict], source_name: str = "fanmolt") -> None:
        """Update with FanMolt agent list (level 2)."""
        self._level = 2
        self._drill_source = source_name
        items = []
        for agent in agents:
            stats = agent.get("stats", {})
            items.append({
                "name": agent.get("name", agent.get("handle", "?")),
                "handle": agent.get("handle", ""),
                "posts": stats.get("posts", 0),
                "comments": stats.get("comments", 0),
                "replies": stats.get("replies", 0),
            })
        self._items = items
        if self._selected_index >= len(items):
            self._selected_index = max(0, len(items) - 1)
        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the displayed item list."""
        render_key = f"{self._level}:{len(self._items)}:{self._selected_index}"
        if render_key == self._last_render_key:
            return
        self._last_render_key = render_key

        lines = []
        if self._level == 2:
            lines.append(f"[bold]← {self._drill_source}[/bold]")
            lines.append("")

        if not self._items:
            lines.append("[dim]No items.[/dim]")
        else:
            for i, item in enumerate(self._items):
                prefix = "▸ " if i == self._selected_index else "  "
                if self._level == 0:
                    enabled = item.get("enabled", True)
                    st = item.get("status", "idle")
                    if not enabled:
                        st = "disabled"
                    icon = _STATUS_ICON.get(st, st)
                    name = item["name"]
                    drill = " ▶" if item.get("drillable") else ""
                    if i == self._selected_index:
                        lines.append(f"[on $surface]{prefix}{icon} {name}{drill}[/on $surface]")
                    else:
                        lines.append(f"{prefix}{icon} {name}{drill}")
                else:
                    name = item["name"]
                    p = item.get("posts", 0)
                    c = item.get("comments", 0)
                    r = item.get("replies", 0)
                    stat_str = f"[dim]{p}p {c}c {r}r[/dim]"
                    if i == self._selected_index:
                        lines.append(f"[on $surface]{prefix}{name}[/on $surface]")
                        lines.append(f"[on $surface]    {stat_str}[/on $surface]")
                    else:
                        lines.append(f"{prefix}{name}")
                        lines.append(f"    {stat_str}")

        self.update("\n".join(lines))

    def get_selected(self) -> dict | None:
        """Return currently selected item."""
        if 0 <= self._selected_index < len(self._items):
            return self._items[self._selected_index]
        return None

    def _on_key(self, event) -> None:
        """Keyboard navigation: Up/Down/Enter/Esc."""
        if not self._items:
            return

        if event.key == "up":
            event.stop()
            event.prevent_default()
            self._selected_index = max(0, self._selected_index - 1)
            self._last_render_key = ""  # force re-render
            self._refresh_list()
            self._emit_selected()

        elif event.key == "down":
            event.stop()
            event.prevent_default()
            self._selected_index = min(len(self._items) - 1, self._selected_index + 1)
            self._last_render_key = ""
            self._refresh_list()
            self._emit_selected()

        elif event.key == "enter":
            event.stop()
            event.prevent_default()
            item = self.get_selected()
            if item and self._level == 0 and item.get("drillable"):
                self.post_message(AutoMasterList.DrillRequested(item["name"]))

        elif event.key == "escape":
            event.stop()
            event.prevent_default()
            if self._level == 2:
                self.post_message(AutoMasterList.BackRequested())

    def _emit_selected(self) -> None:
        """Post ItemSelected message for current selection."""
        item = self.get_selected()
        if item:
            name = item.get("handle", item.get("name", ""))
            self.post_message(AutoMasterList.ItemSelected(name, self._level))


class AutoDetailView(Static):
    """Right detail panel -- shows automation or agent details."""

    DEFAULT_CSS = """
    AutoDetailView {
        width: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)

    def show_automation_detail(self, name: str, data: dict) -> None:
        """Show automation detail info."""
        enabled = data.get("enabled", True)
        status = data.get("status", "idle")
        if not enabled:
            status = "disabled"
        icon = _STATUS_ICON.get(status, status)
        trigger = data.get("trigger", "manual")
        schedule = data.get("schedule", "-") or "-"
        last_run = data.get("last_run", "-") or "-"
        next_run = data.get("next_run", "-") or "-"
        run_count = data.get("run_count", 0)
        last_result = data.get("last_result", "-") or "-"
        last_error = data.get("last_error")
        desc = data.get("description", "")
        workspace = data.get("workspace", "-") or "-"

        if last_run != "-" and "T" in last_run:
            last_run = last_run.replace("T", " ")[:16]
        if next_run != "-" and "T" in next_run:
            next_run = next_run.replace("T", " ")[:16]

        lines = [
            f"[bold]── {name} ──[/bold]",
            "",
            f"  Status      {icon} {status}",
            f"  Trigger     {trigger}",
            f"  Schedule    {schedule}",
            f"  Last Run    {last_run}",
            f"  Next Run    {next_run}",
            f"  Runs        {run_count}",
            f"  Result      {last_result}",
            f"  Workspace   {workspace}",
        ]
        if desc:
            lines.append(f"  Description {desc}")
        if last_error:
            lines.append(f"  [red]Last Error  {last_error}[/red]")

        lines.append("")
        if name.startswith("fanmolt"):
            lines.append("[dim]  \\[r] Run  \\[t] Toggle  \\[Enter] Drill into agents[/dim]")
        else:
            lines.append("[dim]  \\[r] Run  \\[t] Toggle[/dim]")

        self.update("\n".join(lines))

    def show_agent_detail(self, handle: str, agent: dict) -> None:
        """Show FanMolt agent detail info."""
        name = agent.get("name", handle)
        stats = agent.get("stats", {})
        posts = stats.get("posts", 0)
        comments = stats.get("comments", 0)
        replies = stats.get("replies", 0)
        last_hb = agent.get("last_heartbeat_at", "-") or "-"
        last_post = agent.get("last_post_at", "-") or "-"
        category = agent.get("category", "-")

        activity = agent.get("activity", {})
        sched_h = activity.get("schedule_hours", 1)
        max_comments = activity.get("max_comments_per_beat", 10)
        max_replies = activity.get("max_replies_per_beat", 20)

        bp = agent.get("blueprint", {})
        recipes = bp.get("recipes", [])
        recipe_names = [r.get("name", "?") for r in recipes]

        if last_hb != "-" and "T" in last_hb:
            last_hb = last_hb.replace("T", " ")[:16]
        if last_post != "-" and "T" in last_post:
            last_post = last_post.replace("T", " ")[:16]

        lines = [
            f"[bold]── {name} ──[/bold]",
            "",
            f"  Stats       [bold]{posts}[/bold]p  [bold]{comments}[/bold]c  [bold]{replies}[/bold]r",
            f"  Category    {category}",
            f"  Schedule    every {sched_h}h",
            f"  Last Beat   {last_hb}",
            f"  Last Post   {last_post}",
            f"  Limits      {max_comments} comments, {max_replies} replies per beat",
        ]
        if recipe_names:
            lines.append(f"  Recipes     {', '.join(recipe_names)}")
        else:
            lines.append("  Recipes     [dim](none)[/dim]")

        lines.append("")
        lines.append("[dim]  \\[r] Heartbeat  \\[p] Force Post[/dim]")

        self.update("\n".join(lines))

    def show_empty(self) -> None:
        """Show empty state."""
        self.update("[dim]Select an item from the left panel.[/dim]")
