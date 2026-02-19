"""
heysquid.paths — file path constants single source of truth.

All runtime file paths used across the project are defined here.
Import from this module instead of hardcoding paths in each file.
"""

import os

from .config import DATA_DIR_STR as DATA_DIR, TASKS_DIR_STR as TASKS_DIR

# --- Data files ---
MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
WORKING_LOCK_FILE = os.path.join(DATA_DIR, "working.json")
NEW_INSTRUCTIONS_FILE = os.path.join(DATA_DIR, "new_instructions.json")
INTERRUPTED_FILE = os.path.join(DATA_DIR, "interrupted.json")
EXECUTOR_LOCK_FILE = os.path.join(DATA_DIR, "executor.lock")
SESSION_MEMORY_FILE = os.path.join(DATA_DIR, "session_memory.md")
PERMANENT_MEMORY_FILE = os.path.join(DATA_DIR, "permanent_memory.md")

# --- Task index ---
INDEX_FILE = os.path.join(TASKS_DIR, "index.json")

# --- Tuning constants ---
SESSION_MEMORY_MAX_CONVERSATIONS = 50  # 최근 대화 최대 항목 수
WORKING_LOCK_TIMEOUT = 1800  # 30분
