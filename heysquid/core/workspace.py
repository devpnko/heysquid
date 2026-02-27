"""
Multi-project workspace management — heysquid

Key features:
- list_workspaces() - List registered projects
- get_workspace(name) - Get specific workspace info
- switch_workspace(name) - Switch working directory, return context.md
- register_workspace(name, path, description) - Register a new project
- update_progress(name, text) - Update progress status
"""

import os
import json
from datetime import datetime

# Path configuration
from .config import DATA_DIR_STR as DATA_DIR, WORKSPACES_DIR as _WS_DIR

WORKSPACES_DIR = str(_WS_DIR)
WORKSPACES_FILE = os.path.join(DATA_DIR, "workspaces.json")


def _load_workspaces():
    """Load workspaces.json"""
    if not os.path.exists(WORKSPACES_FILE):
        return {}

    try:
        with open(WORKSPACES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Error reading workspaces.json: {e}")
        return {}


def _save_workspaces(data):
    """Save workspaces.json"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(WORKSPACES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_workspaces():
    """
    Return list of registered workspaces.

    Returns:
        dict: {name: {path, description, last_active}, ...}
    """
    return _load_workspaces()


def get_workspace(name):
    """
    Return info for a specific workspace.

    Args:
        name: Workspace name

    Returns:
        dict or None: {path, description, last_active}
    """
    workspaces = _load_workspaces()
    return workspaces.get(name)


def switch_workspace(name):
    """
    Switch working directory + return context.md.

    Args:
        name: Workspace name

    Returns:
        str: context.md contents (empty string if not found)
    """
    workspaces = _load_workspaces()

    if name not in workspaces:
        print(f"[WARN] Workspace '{name}' not found.")
        return ""

    ws = workspaces[name]
    ws_path = ws["path"]

    if not os.path.exists(ws_path):
        print(f"[WARN] Workspace path does not exist: {ws_path}")
        return ""

    # Update last_active
    ws["last_active"] = datetime.now().strftime("%Y-%m-%d")
    _save_workspaces(workspaces)

    print(f"[WORKSPACE] Switched: {name} -> {ws_path}")

    # Read context.md
    context_dir = os.path.join(WORKSPACES_DIR, name)
    context_file = os.path.join(context_dir, "context.md")

    if os.path.exists(context_file):
        try:
            with open(context_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] Error reading context.md: {e}")

    return ""


def register_workspace(name, path, description=""):
    """
    Register a new project workspace.

    Args:
        name: Workspace name (lowercase English recommended)
        path: Absolute project path
        description: Project description
    """
    workspaces = _load_workspaces()

    workspaces[name] = {
        "path": path,
        "description": description,
        "last_active": datetime.now().strftime("%Y-%m-%d")
    }

    _save_workspaces(workspaces)

    # Create workspace context directory
    ws_dir = os.path.join(WORKSPACES_DIR, name)
    os.makedirs(ws_dir, exist_ok=True)

    # Initialize context.md (if not exists)
    context_file = os.path.join(ws_dir, "context.md")
    if not os.path.exists(context_file):
        with open(context_file, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{description}\n\n## Key Files\n\n## Progress\n")

    # Initialize progress.md (if not exists)
    progress_file = os.path.join(ws_dir, "progress.md")
    if not os.path.exists(progress_file):
        with open(progress_file, "w", encoding="utf-8") as f:
            f.write(f"# {name} Progress Log\n\n")

    print(f"[WORKSPACE] Registered: {name} -> {path}")


def update_progress(name, text):
    """
    Update project progress status.

    Args:
        name: Workspace name
        text: Progress status text
    """
    ws_dir = os.path.join(WORKSPACES_DIR, name)
    os.makedirs(ws_dir, exist_ok=True)

    progress_file = os.path.join(ws_dir, "progress.md")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n### [{timestamp}]\n{text}\n"

    with open(progress_file, "a", encoding="utf-8") as f:
        f.write(entry)

    # Update last_active
    workspaces = _load_workspaces()
    if name in workspaces:
        workspaces[name]["last_active"] = datetime.now().strftime("%Y-%m-%d")
        _save_workspaces(workspaces)

    print(f"[PROGRESS] {name}: {text[:50]}...")


def get_progress(name):
    """
    Read project progress log.

    Args:
        name: Workspace name

    Returns:
        str: progress.md contents
    """
    progress_file = os.path.join(WORKSPACES_DIR, name, "progress.md")

    if os.path.exists(progress_file):
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[WARN] Error reading progress.md: {e}")

    return ""


def init_default_workspaces():
    """Register default workspaces (first run) — no-op for pip installs."""
    pass


if __name__ == "__main__":
    print("=" * 60)
    print("heysquid Workspace Management")
    print("=" * 60)

    # Initialize default workspaces
    init_default_workspaces()

    # Print list
    workspaces = list_workspaces()
    if workspaces:
        print(f"\nRegistered workspaces: {len(workspaces)}\n")
        for name, info in workspaces.items():
            print(f"  [{name}]")
            print(f"    Path: {info['path']}")
            print(f"    Description: {info.get('description', '')}")
            print(f"    Last active: {info.get('last_active', 'N/A')}")
            print()
    else:
        print("\nNo registered workspaces.")
