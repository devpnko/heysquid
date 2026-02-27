"""SquidApp -- Textual TUI main application."""

import os
from collections import deque

from textual.app import App, ComposeResult
from textual.binding import Binding

# Project root (config-based)
from heysquid.core.config import PROJECT_ROOT_STR as ROOT

from scripts.tui_textual.screens.chat import ChatScreen
from scripts.tui_textual.screens.kanban import KanbanScreen
from scripts.tui_textual.screens.squad import SquadScreen
from scripts.tui_textual.screens.log import LogScreen
from scripts.tui_textual.screens.skill import SkillScreen
from scripts.tui_textual.widgets.chat_input import ChatInput
from scripts.tui_textual.widgets.command_input import CommandInput
from scripts.tui_textual.widgets.kanban_input import KanbanInput
from scripts.tui_textual.widgets.tab_bar import TabBar
from scripts.tui_textual.commands import send_chat_message, execute_command
from scripts.tui_textual.data_poller import load_stream_lines, STREAM_BUFFER_SIZE

MODE_CHAT = 0
MODE_KANBAN = 1
MODE_SQUAD = 2
MODE_LOG = 3
MODE_SKILL = 4
MODE_NAMES = {MODE_CHAT: "CHAT", MODE_KANBAN: "KANBAN", MODE_SQUAD: "SQUAD", MODE_LOG: "LOG", MODE_SKILL: "AUTO"}
MODE_COUNT = 5

CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "squid.tcss")


class SquidApp(App):
    """SQUID TUI -- Textual-based"""

    TITLE = "SQUID TUI"
    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("ctrl+c", "copy_selection", "Copy", priority=True),
        Binding("ctrl+1", "mode_chat", "Chat", priority=True),
        Binding("ctrl+2", "mode_kanban", "Kanban", priority=True),
        Binding("ctrl+3", "mode_squad", "Squad", priority=True),
        Binding("ctrl+4", "mode_log", "Log", priority=True),
        Binding("ctrl+5", "mode_skill", "Skill", priority=True),
        Binding("ctrl+left", "mode_prev", "Prev", priority=True),
        Binding("ctrl+right", "mode_next", "Next", priority=True),
        Binding("ctrl+q", "quit_app", "Quit", priority=True),
        Binding("q", "quit_app", "Quit", priority=False),
        Binding("slash", "command_mode", "Command", priority=False),
    ]

    def __init__(self):
        super().__init__()
        self._mode = MODE_CHAT
        self._stream_buffer = deque(maxlen=STREAM_BUFFER_SIZE)
        self._stream_pos = 0
        self._flash_msg = ""
        self._flash_timer = None
        self._screens = {}

    def compose(self) -> ComposeResult:
        yield from ()

    def on_mount(self) -> None:
        """Install Chat screen on app start + set up polling timer."""
        chat = ChatScreen()
        kanban = KanbanScreen()
        squad = SquadScreen()
        log = LogScreen()
        skill = SkillScreen()

        self.install_screen(chat, name="chat")
        self.install_screen(kanban, name="kanban")
        self.install_screen(squad, name="squad")
        self.install_screen(log, name="log")
        self.install_screen(skill, name="skill")

        self._screens = {"chat": chat, "kanban": kanban, "squad": squad, "log": log, "skill": skill}

        self.push_screen("chat")
        self._mode = MODE_CHAT

        # Data polling timer: 2-second interval
        self.set_interval(2.0, self._poll_data)
        # Initial data load (after compose completes)
        self.call_after_refresh(self._poll_data)

    def _poll_data(self) -> None:
        """Periodic data polling -- swallow any exception to guarantee next poll."""
        try:
            self._stream_pos = load_stream_lines(self._stream_pos, self._stream_buffer)
        except Exception:
            pass

        screen = self.screen
        flash = self._flash_msg

        try:
            if isinstance(screen, ChatScreen):
                screen.refresh_data(flash=flash)
            elif isinstance(screen, KanbanScreen):
                screen.refresh_data(flash=flash)
            elif isinstance(screen, SquadScreen):
                screen.refresh_data(flash=flash)
            elif isinstance(screen, LogScreen):
                screen.refresh_data(self._stream_buffer, flash=flash)
            elif isinstance(screen, SkillScreen):
                screen.refresh_data(flash=flash)
        except Exception:
            pass  # Before compose completes or data error -- retry on next poll

    def _switch_mode(self, new_mode: int) -> None:
        """Switch mode."""
        mode_map = {MODE_CHAT: "chat", MODE_KANBAN: "kanban", MODE_SQUAD: "squad", MODE_LOG: "log", MODE_SKILL: "skill"}
        self._mode = new_mode
        self.switch_screen(mode_map[new_mode])
        # Update TabBar active tab
        try:
            tab_bar = self.screen.query_one(TabBar)
            tab_bar.set_active(new_mode)
        except Exception:
            pass
        # Focus input when switching to Chat/Kanban mode
        if new_mode == MODE_CHAT:
            try:
                self.screen.query_one(ChatInput).focus()
            except Exception:
                pass
        elif new_mode == MODE_KANBAN:
            try:
                self.screen.query_one(KanbanInput).focus()
            except Exception:
                pass
        # Immediately load data after switch
        self.call_after_refresh(self._poll_data)

    def action_mode_chat(self) -> None:
        """Ctrl+1 -> Chat mode"""
        self._switch_mode(MODE_CHAT)

    def action_mode_kanban(self) -> None:
        """Ctrl+2 -> Kanban mode"""
        self._switch_mode(MODE_KANBAN)

    def action_mode_squad(self) -> None:
        """Ctrl+3 -> Squad mode"""
        self._switch_mode(MODE_SQUAD)

    def action_mode_log(self) -> None:
        """Ctrl+4 -> Log mode"""
        self._switch_mode(MODE_LOG)

    def action_mode_skill(self) -> None:
        """Ctrl+5 -> Skill mode"""
        self._switch_mode(MODE_SKILL)

    def action_mode_prev(self) -> None:
        """Ctrl+Left -> previous mode"""
        self._switch_mode((self._mode - 1) % MODE_COUNT)

    def action_mode_next(self) -> None:
        """Ctrl+Right -> next mode"""
        self._switch_mode((self._mode + 1) % MODE_COUNT)

    def action_copy_selection(self) -> None:
        """Ctrl+C -> copy selected text, or show quit hint if none"""
        selected = self.screen.get_selected_text()
        if selected:
            self.copy_to_clipboard(selected)
            self.screen.clear_selection()
            self._set_flash(f"✓ Copied ({len(selected)} chars)")
        else:
            for key, active_binding in self.active_bindings.items():
                if active_binding.binding.action in ("quit", "quit_app", "app.quit"):
                    self.notify(f"Press [b]{key}[/b] to quit", title="Quit?")
                    return

    def action_quit_app(self) -> None:
        """q -> quit (ignored if typing in Chat/Kanban input)"""
        if isinstance(self.screen, ChatScreen):
            try:
                input_widget = self.screen.query_one(ChatInput)
                if input_widget.text:
                    return
            except Exception:
                pass
        elif isinstance(self.screen, KanbanScreen):
            try:
                input_widget = self.screen.query_one(KanbanInput)
                if input_widget.value:
                    return
            except Exception:
                pass
        self.exit()

    def action_command_mode(self) -> None:
        """/ command mode in Squad/Log/Skill modes (kanban uses dedicated input)"""
        if isinstance(self.screen, (SquadScreen, LogScreen, SkillScreen)):
            try:
                cmd_input = self.screen.query_one(CommandInput)
                cmd_input.show()
            except Exception:
                pass

    def copy_to_clipboard(self, text: str) -> None:
        """Copy to clipboard via macOS pbcopy (instead of OSC 52)."""
        import subprocess
        try:
            subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"),
                capture_output=True, timeout=5,
            )
        except Exception:
            pass
        super().copy_to_clipboard(text)

    def _set_flash(self, msg: str) -> None:
        """Set flash message (auto-clear after 5 seconds)."""
        self._flash_msg = msg
        if self._flash_timer:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(5.0, self._clear_flash)

    def _clear_flash(self) -> None:
        """Clear flash message."""
        self._flash_msg = ""
        if isinstance(self.screen, ChatScreen):
            self.screen.clear_flash()

    # --- Message event handlers ---

    def on_chat_input_chat_submitted(self, event: ChatInput.ChatSubmitted) -> None:
        """Chat input submitted."""
        result = send_chat_message(event.value, self._stream_buffer)
        if result:
            self._set_flash(result)
        self._poll_data()

    def on_command_input_command_submitted(self, event: CommandInput.CommandSubmitted) -> None:
        """Command input submitted (Squad/Log/Skill)."""
        result = execute_command(event.value, self._stream_buffer)
        if result:
            self._set_flash(result)
        self._poll_data()

    def on_kanban_input_kanban_command_submitted(self, event: KanbanInput.KanbanCommandSubmitted) -> None:
        """Kanban-specific command submitted -- executes without / prefix."""
        cmd_text = event.value.strip()
        is_info = cmd_text.lower().startswith("info")
        result = execute_command(cmd_text, self._stream_buffer)
        if result and is_info and isinstance(self.screen, KanbanScreen):
            # Show info results in info panel
            self.screen.show_info(result)
        elif result:
            # Non-info commands use flash + hide info panel
            if isinstance(self.screen, KanbanScreen):
                self.screen.hide_info()
            self._set_flash(result)
        self._poll_data()


def main():
    """Entry point."""
    app = SquidApp()
    app.run()


if __name__ == "__main__":
    main()
