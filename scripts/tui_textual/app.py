"""SquidApp — Textual TUI 메인 앱"""

import os
import sys
from collections import deque

from textual.app import App, ComposeResult
from textual.binding import Binding

# 프로젝트 루트
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from scripts.tui_textual.screens.chat import ChatScreen
from scripts.tui_textual.screens.squad import SquadScreen
from scripts.tui_textual.screens.log import LogScreen
from scripts.tui_textual.screens.skill import SkillScreen
from scripts.tui_textual.widgets.chat_input import ChatInput
from scripts.tui_textual.widgets.command_input import CommandInput
from scripts.tui_textual.commands import send_chat_message, execute_command
from scripts.tui_textual.data_poller import load_stream_lines, STREAM_BUFFER_SIZE

MODE_CHAT = 0
MODE_SQUAD = 1
MODE_LOG = 2
MODE_SKILL = 3
MODE_NAMES = {MODE_CHAT: "CHAT", MODE_SQUAD: "SQUAD", MODE_LOG: "LOG", MODE_SKILL: "SKILL"}
MODE_COUNT = 4

CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "squid.tcss")


class SquidApp(App):
    """🦑 SQUID TUI — Textual 기반"""

    TITLE = "SQUID TUI"
    CSS_PATH = CSS_PATH

    BINDINGS = [
        Binding("ctrl+1", "mode_chat", "Chat", priority=True),
        Binding("ctrl+2", "mode_squad", "Squad", priority=True),
        Binding("ctrl+3", "mode_log", "Log", priority=True),
        Binding("ctrl+4", "mode_skill", "Skill", priority=True),
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
        """앱 시작 시 Chat 스크린 설치 + 폴링 타이머"""
        chat = ChatScreen()
        squad = SquadScreen()
        log = LogScreen()
        skill = SkillScreen()

        self.install_screen(chat, name="chat")
        self.install_screen(squad, name="squad")
        self.install_screen(log, name="log")
        self.install_screen(skill, name="skill")

        self._screens = {"chat": chat, "squad": squad, "log": log, "skill": skill}

        self.push_screen("chat")
        self._mode = MODE_CHAT

        # 데이터 폴링 타이머: 2초 간격
        self.set_interval(2.0, self._poll_data)
        # 초기 데이터 로드 (compose 완료 후)
        self.call_after_refresh(self._poll_data)

    def _poll_data(self) -> None:
        """주기적 데이터 폴링"""
        # Stream 로그 항상 로드 (Log 모드에서 필요)
        self._stream_pos = load_stream_lines(self._stream_pos, self._stream_buffer)

        # 활성 스크린만 갱신
        screen = self.screen
        flash = self._flash_msg

        try:
            if isinstance(screen, ChatScreen):
                screen.refresh_data(flash=flash)
            elif isinstance(screen, SquadScreen):
                screen.refresh_data(flash=flash)
            elif isinstance(screen, LogScreen):
                screen.refresh_data(self._stream_buffer, flash=flash)
            elif isinstance(screen, SkillScreen):
                screen.refresh_data(flash=flash)
        except Exception:
            pass  # compose 완료 전이면 무시

    def _switch_mode(self, new_mode: int) -> None:
        """모드 전환"""
        mode_map = {MODE_CHAT: "chat", MODE_SQUAD: "squad", MODE_LOG: "log", MODE_SKILL: "skill"}
        self._mode = new_mode
        self.switch_screen(mode_map[new_mode])
        # Chat 모드로 돌아오면 Input에 포커스
        if new_mode == MODE_CHAT:
            try:
                self.screen.query_one(ChatInput).focus()
            except Exception:
                pass
        # 전환 후 즉시 데이터 로드
        self.call_after_refresh(self._poll_data)

    def action_mode_chat(self) -> None:
        """Ctrl+1 → Chat 모드"""
        self._switch_mode(MODE_CHAT)

    def action_mode_squad(self) -> None:
        """Ctrl+2 → Squad 모드"""
        self._switch_mode(MODE_SQUAD)

    def action_mode_log(self) -> None:
        """Ctrl+3 → Log 모드"""
        self._switch_mode(MODE_LOG)

    def action_mode_skill(self) -> None:
        """Ctrl+4 → Skill 모드"""
        self._switch_mode(MODE_SKILL)

    def action_mode_prev(self) -> None:
        """Ctrl+← → 이전 모드"""
        self._switch_mode((self._mode - 1) % MODE_COUNT)

    def action_mode_next(self) -> None:
        """Ctrl+→ → 다음 모드"""
        self._switch_mode((self._mode + 1) % MODE_COUNT)

    def action_quit_app(self) -> None:
        """q → 종료 (Chat 모드에서 입력 중이면 무시)"""
        if isinstance(self.screen, ChatScreen):
            try:
                input_widget = self.screen.query_one(ChatInput)
                if input_widget.text:
                    return  # 입력 중이면 q를 문자로 처리
            except Exception:
                pass
        self.exit()

    def action_command_mode(self) -> None:
        """Squad/Log 모드에서 / 커맨드 모드"""
        if isinstance(self.screen, (SquadScreen, LogScreen, SkillScreen)):
            try:
                cmd_input = self.screen.query_one(CommandInput)
                cmd_input.show()
            except Exception:
                pass

    def copy_to_clipboard(self, text: str) -> None:
        """macOS pbcopy로 클립보드 복사 (OSC 52 대신)"""
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
        """flash 메시지 설정 (5초 후 자동 클리어)"""
        self._flash_msg = msg
        if self._flash_timer:
            self._flash_timer.stop()
        self._flash_timer = self.set_timer(5.0, self._clear_flash)

    def _clear_flash(self) -> None:
        """flash 메시지 클리어"""
        self._flash_msg = ""
        if isinstance(self.screen, ChatScreen):
            self.screen.clear_flash()

    # --- 메시지 이벤트 핸들러 ---

    def on_chat_input_chat_submitted(self, event: ChatInput.ChatSubmitted) -> None:
        """Chat 입력 제출"""
        result = send_chat_message(event.value, self._stream_buffer)
        if result:
            self._set_flash(result)
        self._poll_data()

    def on_command_input_command_submitted(self, event: CommandInput.CommandSubmitted) -> None:
        """커맨드 입력 제출"""
        result = execute_command(event.value, self._stream_buffer)
        if result:
            self._set_flash(result)
        self._poll_data()


def main():
    """엔트리포인트"""
    app = SquidApp()
    app.run()


if __name__ == "__main__":
    main()
