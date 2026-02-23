"""Deep Work Loop -- iterative refinement skill for maximum quality.

PM triggers this skill when user requests deep/iterative work.
State is persisted in data/deep_work_state.json for crash recovery.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from ...core.config import DATA_DIR

logger = logging.getLogger(__name__)

SKILL_META = {
    "name": "deep_work",
    "description": "Deep Work Loop -- iterative refinement for maximum quality",
    "trigger": "manual",
    "enabled": True,
}

STATE_FILE = DATA_DIR / "deep_work_state.json"

PHASES = ("research", "develop", "review", "test")
PHASE_AGENTS = {
    "research": "researcher",
    "develop": "developer",
    "review": "reviewer",
    "test": "tester",
}
DEFAULT_MAX_ITERATIONS = 10
EARLY_EXIT_STREAK = 3  # consecutive all-pass iterations to auto-finish


def _load_state() -> dict | None:
    """Load current deep work state. Returns None if no active loop."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _save_state(state: dict) -> None:
    """Persist state to disk."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def get_state() -> dict | None:
    """Return current loop state. PM calls this to check progress."""
    return _load_state()


def start_loop(task: str, max_iterations: int = DEFAULT_MAX_ITERATIONS,
               plan: str = "") -> dict:
    """Initialize a new deep work loop.

    Args:
        task: What we're working on (e.g. "API performance optimization")
        max_iterations: User-configured iteration count (SQUID recommends 10)
        plan: PM's initial plan text

    Returns:
        The initial state dict.
    """
    state = {
        "active": True,
        "task": task,
        "max_iterations": max_iterations,
        "current_iteration": 0,
        "plan": plan,
        "started_at": datetime.now().isoformat(),
        "iterations": [],
        "status": "running",
        "final_summary": None,
    }
    _save_state(state)
    logger.info("Deep Work started: %s (%d iterations)", task, max_iterations)
    return state


def record_iteration(iteration: int, phase: str, agent: str,
                     result: str, passed: bool,
                     issues: list[str] | None = None) -> dict:
    """Record a single phase result within an iteration.

    Args:
        iteration: 1-based iteration number
        phase: One of "research", "develop", "review", "test"
        agent: Agent name that performed this phase
        result: Summary of what the agent did/found
        passed: Whether this phase's quality check passed
        issues: List of issues found (for failed phases)

    Returns:
        Updated state dict.
    """
    state = _load_state()
    if not state or not state.get("active"):
        raise RuntimeError("No active deep work loop")

    # Ensure iteration entry exists
    while len(state["iterations"]) < iteration:
        state["iterations"].append({
            "n": len(state["iterations"]) + 1,
            "phases": {},
            "gate_passed": False,
            "summary": "",
        })

    entry = state["iterations"][iteration - 1]
    phase_data = {
        "agent": agent,
        "result": result,
        "passed": passed,
    }
    if issues:
        phase_data["issues"] = issues
    entry["phases"][phase] = phase_data

    state["current_iteration"] = iteration
    _save_state(state)
    return state


def check_quality_gate(iteration: int) -> bool:
    """Check if all phases in an iteration passed.

    Returns True if all 4 phases exist and passed.
    """
    state = _load_state()
    if not state or iteration < 1 or iteration > len(state["iterations"]):
        return False

    entry = state["iterations"][iteration - 1]
    phases = entry.get("phases", {})

    all_passed = all(
        phases.get(p, {}).get("passed", False) for p in PHASES
    )

    # Update gate status
    entry["gate_passed"] = all_passed
    _save_state(state)
    return all_passed


def set_iteration_summary(iteration: int, summary: str) -> None:
    """Set the summary for a completed iteration."""
    state = _load_state()
    if not state or iteration < 1 or iteration > len(state["iterations"]):
        return
    state["iterations"][iteration - 1]["summary"] = summary
    _save_state(state)


def should_early_exit() -> bool:
    """Check if we should exit early (N consecutive all-pass iterations)."""
    state = _load_state()
    if not state:
        return False

    iterations = state.get("iterations", [])
    if len(iterations) < EARLY_EXIT_STREAK:
        return False

    recent = iterations[-EARLY_EXIT_STREAK:]
    return all(it.get("gate_passed", False) for it in recent)


def get_failed_issues(iteration: int) -> list[str]:
    """Get all issues from failed phases in a given iteration."""
    state = _load_state()
    if not state or iteration < 1 or iteration > len(state["iterations"]):
        return []

    entry = state["iterations"][iteration - 1]
    issues = []
    for phase in PHASES:
        phase_data = entry.get("phases", {}).get(phase, {})
        if not phase_data.get("passed", True):
            issues.extend(phase_data.get("issues", []))
            if not phase_data.get("issues") and phase_data.get("result"):
                issues.append(f"[{phase}] {phase_data['result'][:200]}")
    return issues


def finish_loop(summary: str) -> dict:
    """Complete the deep work loop with a final summary.

    Returns the final state dict.
    """
    state = _load_state()
    if not state:
        raise RuntimeError("No active deep work loop")

    state["active"] = False
    state["status"] = "completed"
    state["final_summary"] = summary
    state["finished_at"] = datetime.now().isoformat()
    _save_state(state)
    logger.info("Deep Work completed: %s", state["task"])
    return state


def abort_loop(reason: str = "user cancelled") -> dict | None:
    """Abort an active loop."""
    state = _load_state()
    if not state or not state.get("active"):
        return None

    state["active"] = False
    state["status"] = "aborted"
    state["final_summary"] = reason
    state["finished_at"] = datetime.now().isoformat()
    _save_state(state)
    logger.info("Deep Work aborted: %s", reason)
    return state


def execute(**kwargs):
    """Skill plugin entry point. Returns current state for dashboard."""
    state = get_state()
    if state and state.get("active"):
        return {
            "status": "running",
            "task": state["task"],
            "iteration": f"{state['current_iteration']}/{state['max_iterations']}",
        }
    return {"status": "idle"}
