"""M0.5 structural safeguard tests — common fixtures"""

import json
import os
import tempfile
import shutil

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Isolated temporary data directory"""
    return tmp_path


@pytest.fixture
def messages_file(tmp_data_dir):
    """Empty messages.json path"""
    return str(tmp_data_dir / "telegram_messages.json")


@pytest.fixture
def sample_messages():
    """Sample message data for testing"""
    return {
        "messages": [
            {
                "message_id": 100,
                "type": "user",
                "channel": "telegram",
                "chat_id": 12345,
                "text": "안녕",
                "files": [],
                "timestamp": "2026-02-21 10:00:00",
                "processed": False,
            },
            {
                "message_id": 101,
                "type": "user",
                "channel": "telegram",
                "chat_id": 12345,
                "text": "작업 해줘",
                "files": [],
                "timestamp": "2026-02-21 10:01:00",
                "processed": False,
            },
            {
                "message_id": 102,
                "type": "bot",
                "channel": "system",
                "chat_id": 12345,
                "text": "알겠어요",
                "files": [],
                "timestamp": "2026-02-21 10:01:30",
                "processed": True,
            },
        ],
        "last_update_id": 999,
    }
