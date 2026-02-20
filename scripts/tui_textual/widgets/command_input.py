"""CommandInput — Squad/Log 모드의 : 커맨드 입력"""

from textual.widgets import Input
from textual.message import Message


class CommandInput(Input):
    """Squad/Log 모드에서 : 으로 시작하는 커맨드 입력"""

    DEFAULT_CSS = """
    CommandInput {
        dock: bottom;
        height: 1;
        margin: 0 1;
        display: none;
    }
    CommandInput.visible {
        display: block;
    }
    """

    class CommandSubmitted(Message):
        """커맨드 제출 이벤트"""
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    def __init__(self, **kwargs):
        super().__init__(
            placeholder=":커맨드 입력...",
            **kwargs,
        )

    def show(self) -> None:
        """커맨드 입력 표시"""
        self.add_class("visible")
        self.value = ""
        self.focus()

    def hide(self) -> None:
        """커맨드 입력 숨기기"""
        self.remove_class("visible")
        self.value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter 키 처리"""
        event.stop()
        text = self.value.strip()
        if text:
            self.post_message(CommandInput.CommandSubmitted(text))
        self.hide()

    def _on_key(self, event) -> None:
        """Escape로 커맨드 모드 종료"""
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            self.hide()
