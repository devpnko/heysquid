# Contributing to heysquid

Thanks for your interest in contributing to heysquid! Here's how to get started.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/devpnko/heysquid.git
cd heysquid

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode with all extras
pip install -e ".[all]"

# Create required directories
mkdir -p data tasks workspaces logs

# Copy environment template
cp heysquid/.env.example heysquid/.env
# Edit .env with your Telegram bot token and user ID
```

## Project Structure

- `heysquid/` — Core Python package (what gets installed via pip)
- `scripts/` — Shell scripts for daemon management and monitoring
- `tests/` — Test suite
- `data/` — Runtime data (gitignored, created at runtime)

## Making Changes

1. **Fork** the repository
2. **Create a branch** from `main`: `git checkout -b feat/my-feature`
3. **Make your changes** — keep commits focused and atomic
4. **Test** your changes work with `heysquid status` and the TUI
5. **Submit a PR** against `main`

## Commit Messages

We follow conventional commits:

```
feat: add Slack channel adapter
fix: prevent duplicate executor processes
docs: update Quick Start section
refactor: extract memory module from telegram_bot
```

## Code Style

- Python 3.10+ (use type hints where helpful, but don't over-annotate)
- Keep it simple — no premature abstractions
- Existing patterns > new patterns (check how similar code works before adding yours)

## Adding a New Channel

Channels live in `heysquid/channels/`. To add a new messaging platform:

1. Create `heysquid/channels/your_channel.py`
2. Implement the listener (poll for new messages, trigger executor)
3. Add a plist template in `heysquid/templates/launchd/`
4. Register in `heysquid/core/daemon.py`
5. Add optional dependency group in `pyproject.toml`

## Adding a New Skill or Automation

Plugins use auto-discovery — no registration step needed.

```python
# heysquid/skills/your_skill/__init__.py

SKILL_META = {
    "name": "your_skill",
    "description": "What this skill does",
    "trigger": "manual",       # "manual" | "webhook"
    "enabled": True,
}

def execute(**kwargs) -> dict:
    """
    kwargs: triggered_by, chat_id, args, payload, callback_url
    """
    return {"ok": True}
```

Drop the folder into `skills/` (manual) or `automations/` (scheduled) — the plugin loader picks it up automatically. See [skills/GUIDE.md](heysquid/skills/GUIDE.md) for the full reference.

## Questions?

Open an issue on GitHub — we're happy to help!
