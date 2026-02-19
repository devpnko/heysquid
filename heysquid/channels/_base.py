"""heysquid.channels._base — abstract channel adapter."""

from abc import ABC, abstractmethod


class ChannelAdapter(ABC):
    """Base class for messaging channel integrations."""

    @abstractmethod
    def send_message(self, chat_id, text, **kwargs):
        ...

    @abstractmethod
    def send_file(self, chat_id, file_path, **kwargs):
        ...
