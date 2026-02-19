"""
heysquid.config — path resolution single source of truth.

Resolution priority:
1. HEYSQUID_HOME env var (explicit override)
2. Dev mode: parent of this package has data/ + CLAUDE.md → use that directory
3. Default: ~/.heysquid/
"""

import os
from pathlib import Path

_pkg_dir = Path(__file__).resolve().parent          # heysquid/core/
_pkg_root = _pkg_dir.parent                         # heysquid/
_candidate_root = _pkg_root.parent                  # parent of heysquid/


def _detect_project_root() -> Path:
    # 1. Explicit env var
    env_home = os.environ.get("HEYSQUID_HOME")
    if env_home:
        return Path(env_home)

    # 2. Dev mode: parent has data/ AND CLAUDE.md
    if (_candidate_root / "data").is_dir() and (_candidate_root / "CLAUDE.md").is_file():
        return _candidate_root

    # 3. Default: ~/.heysquid/
    return Path.home() / ".heysquid"


PROJECT_ROOT: Path = _detect_project_root()
DATA_DIR: Path = PROJECT_ROOT / "data"
TASKS_DIR: Path = PROJECT_ROOT / "tasks"
WORKSPACES_DIR: Path = PROJECT_ROOT / "workspaces"
LOGS_DIR: Path = PROJECT_ROOT / "logs"
PACKAGE_DIR: Path = _pkg_root

# Ensure str compatibility for os.path.join / open() callers
PROJECT_ROOT_STR: str = str(PROJECT_ROOT)
DATA_DIR_STR: str = str(DATA_DIR)
TASKS_DIR_STR: str = str(TASKS_DIR)


def get_env_path() -> str:
    """Return the .env file path.

    Dev mode: heysquid/.env (inside package dir, backwards compat)
    Installed mode: DATA_DIR/.env
    """
    dev_env = _pkg_root / ".env"
    if dev_env.is_file():
        return str(dev_env)
    return str(DATA_DIR / ".env")


def get_template_path(name: str) -> str:
    """Return path to a bundled template file."""
    return str(_pkg_root / "templates" / name)
