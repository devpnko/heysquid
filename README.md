# heysquid 🦑

**Your personal PM agent that never sleeps.**

heysquid turns [Claude Code](https://docs.anthropic.com/en/docs/claude-code) into an always-on project manager you can text from Telegram. Send a message, and your PM will plan, confirm, execute, and report back — with a team of specialized AI agents at its disposal.

## Why heysquid?

Most AI coding tools wait for you to sit at a computer. heysquid works while you're away:

- **PM Protocol** — Every task follows Plan → Confirm → Execute → Report. No surprises.
- **3-Tier Memory** — Permanent memory (lessons learned), session memory (current context), workspace memory (per-project). Your PM remembers everything.
- **Agent Team** — 6 specialists auto-dispatched by the PM. The right model for the right job.
- **Always-On** — Daemon-based architecture. Send a Telegram message at 3am, get a response in seconds.
- **Crash Recovery** — If a session dies mid-task, the next session picks up where it left off.

## Quick Start

```bash
pip install heysquid
heysquid init       # Interactive setup (Telegram token, user ID)
heysquid start      # Start the daemon
```

That's it. Send a message to your Telegram bot and start working.

### Prerequisites

- **macOS** (launchd-based daemon; Linux support planned)
- **Python 3.10+**
- **Claude Code CLI** — [Install guide](https://docs.anthropic.com/en/docs/claude-code)
- **Claude Max subscription** — No additional API costs ($0 beyond subscription)
- **Telegram bot token** — Get one from [@BotFather](https://t.me/BotFather)

## How It Works

```
You (Telegram) → Listener → Executor → Claude Code (PM mode) → You (Telegram)
                                              ↕
                                    Agent Team (6 specialists)
                                              ↕
                                    Memory (permanent / session / workspace)
```

1. You send a message on Telegram
2. The **listener** daemon detects it within 10 seconds
3. **executor.sh** launches Claude Code in PM mode
4. The PM reads your message and decides:
   - Chat → responds naturally
   - Task request → explains plan, asks for confirmation
   - Approval → dispatches agents, executes, reports back
5. After completing work, enters **standby loop** (polls every 30s, stays alive indefinitely)

## Agent Team

The PM orchestrates 6 specialized agents, auto-escalating to stronger models when needed:

| Role | Agent | Model | Specialty |
|------|-------|-------|-----------|
| 🦑 PM | squid | Opus | Decision-making, orchestration, user communication |
| 🐙 Researcher | octopus | Haiku→Sonnet | Code exploration, web research, analysis |
| 🦈 Developer | shark | Opus | Implementation, bug fixes, refactoring |
| 🐢 Reviewer | turtle | Sonnet | Code review, security audit |
| 🐡 Tester | pufferfish | Haiku | Test execution, build verification |
| 🦞 Writer | lobster | Sonnet | Documentation, content, copywriting |

**Escalation**: If Haiku fails → auto-promote to Sonnet → Opus. No manual intervention.

## Features

| Feature | Description |
|---------|-------------|
| **Telegram Control** | Chat naturally, request tasks, approve plans — all from your phone |
| **Interrupt Anytime** | Send "stop" / "cancel" to halt current work within 10 seconds |
| **Daily Briefing** | Automated morning briefing with project status + curated tech news |
| **Multi-Workspace** | Switch between projects seamlessly. Each has its own context |
| **Real-time Dashboard** | Browser-based agent status visualization |
| **TUI Monitor** | Terminal UI for live monitoring and direct PM interaction |
| **Crash Recovery** | Detects interrupted sessions and resumes automatically |
| **Session Memory** | Conversations persist across sessions. Your PM knows your preferences |

## CLI Commands

```bash
heysquid init       # Interactive setup wizard
heysquid start      # Start listener + scheduler daemons
heysquid stop       # Stop all daemons and processes
heysquid restart    # Stop + Start
heysquid status     # Show daemon status, processes, lock files
heysquid logs       # View recent logs (add -f to follow)
heysquid tui        # Launch terminal UI monitor
```

## Monitoring

```bash
# Terminal UI (interactive, can send messages to PM)
heysquid tui

# Browser dashboard
open http://localhost:8420/dashboard.html

# Raw logs
heysquid logs -f
```

## Memory System

heysquid uses a 3-tier memory architecture:

| Layer | File | Scope | Purpose |
|-------|------|-------|---------|
| **Permanent** | `data/permanent_memory.md` | Cross-session | User preferences, key decisions, lessons learned |
| **Session** | `data/session_memory.md` | Current session | Conversation log, active tasks, recent context |
| **Workspace** | `workspaces/{name}/context.md` | Per-project | Project-specific knowledge and progress |

The PM auto-saves session memory every 30 minutes and writes session highlights to permanent memory on exit.

## Project Structure

```
heysquid/
├── heysquid/               # Core package
│   ├── core/               # Config, CLI, daemon, agents registry
│   ├── channels/           # Messaging adapters (Telegram, Slack, Discord)
│   ├── skills/             # Pluggable skills (briefing, threads, marketing)
│   ├── memory/             # Session, tasks, crash recovery
│   ├── dashboard/          # Agent status visualization
│   └── templates/          # Plist templates, env examples
├── scripts/                # Shell scripts (executor, setup, monitoring)
├── data/                   # Runtime data (gitignored)
├── tasks/                  # Per-message task memory (gitignored)
├── workspaces/             # Project contexts (gitignored)
└── logs/                   # Execution logs (gitignored)
```

## Configuration

All configuration lives in `heysquid/.env`:

```env
# Required
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ALLOWED_USERS=your_telegram_id

# Optional
TELEGRAM_POLLING_INTERVAL=10    # seconds (default: 10)
```

Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot).

## How It's Built

heysquid is a thin orchestration layer on top of Claude Code:

- **No custom LLM calls** — Everything runs through Claude Code CLI (`claude -p`)
- **No API keys needed** — Uses your Claude Max subscription
- **Claude Code Agent Teams** — Sub-agents are Claude Code's native Task tool
- **Daemon = launchd** — macOS native job scheduling, zero dependencies
- **Memory = markdown files** — Human-readable, git-friendly, no database

## Roadmap

- [x] PM protocol (plan → confirm → execute → report)
- [x] Agent team with auto-escalation
- [x] 3-tier memory system
- [x] Crash recovery
- [x] `pip install heysquid`
- [ ] Multi-channel (Slack, Discord adapters)
- [ ] Linux support (systemd)
- [ ] Department mode (parallel Claude Code processes)
- [ ] Voice input (Whisper → task instruction)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[Apache License 2.0](LICENSE)
