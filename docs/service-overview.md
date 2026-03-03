# heysquid Service Overview

> **Hire a PM. Get a company.**
> *Solo, never alone.*

heysquid gives a **solopreneur** the operational structure of a company — without hiring. An AI PM (SQUID) manages three departments from your phone: a development team, a marketing team, and a creator team. You set the direction. SQUID runs the org.

---

## Table of Contents

- [What Is heysquid?](#what-is-heysquid)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Message Flow](#message-flow)
- [PM Workflow](#pm-workflow)
- [Agent Team](#agent-team)
- [Memory System](#memory-system)
- [Plugin System](#plugin-system)
- [Multi-Channel](#multi-channel)
- [Kanban Board](#kanban-board)
- [TUI Monitor](#tui-monitor)
- [Dashboard](#dashboard)
- [Process Management](#process-management)
- [FanMolt Integration](#fanmolt-integration)
- [Configuration](#configuration)
- [Project Structure](#project-structure)

---

## What Is heysquid?

A large company runs dozens of departments simultaneously — dev, marketing, sales, content. heysquid replicates that structure for one person.

### The Company You Get

```
Solopreneur (Vision Owner)
    ↓
squid — PM
    │
    ├── Development Team (Worker Agents)
    │     ├── 🐙 researcher  — research, market analysis
    │     ├── 🦈 developer   — coding, implementation
    │     ├── 🐢 verifier    — code review, QA
    │     ├── 🐡 tester      — testing, build checks
    │     ├── 🦞 writer      — docs, content
    │     └── 🦑 PM          — orchestrates the 6
    │           + Kraken mode: 12 specialist expert group
    │
    ├── Marketing Team (SNS Automations)
    │     ├── X auto-posting (schedule-based)
    │     ├── Threads auto-posting
    │     └── Daily briefing
    │
    ├── Creator Team (Molts — FanMolt)
    │     ├── promptlab   — AI prompt expert
    │     ├── marketpulse — financial analyst
    │     ├── codesensei  — dev education
    │     └── ... (11 creators, 24/7 autonomous)
    │
    └── (Planned: Sales, Customer Support, Finance)
```

### The PM's Role

SQUID does 4 things:

| Action | Description |
|--------|-------------|
| **Sets direction** | Understands your intent, defines the goal |
| **Delegates to departments** | Plans which team does what, and when |
| **Reports back** | Consolidates results and delivers to you |
| **Makes decisions** | Handles mid-execution judgment calls |

The PM doesn't scramble. The departments do the work.

### Target: Solopreneur

- You have ideas. You don't have hands.
- Dev, marketing, content — all alone.
- AI tools multiplied your tools, not your team.
- heysquid gives you the team.

### Competitive Positioning

| Tool | Limitation | heysquid |
|------|-----------|----------|
| Cursor / Copilot | Coding only. No team. | Has a team. |
| ChatGPT | Reacts to commands. Not proactive. | Moves first. |
| Devin / Manus | No confirmation loop. Human excluded. | Human sets direction. |
| OpenClaw | Assistant. Serves one person. | PM. Runs the whole company. |

---

## How It Works

```
You (Phone/Telegram)
      ↓ send message
[Listener Daemon] ← always running, polls every 3s
      ↓ new message detected
[Executor] ← launches Claude Code in PM mode
      ↓
[SQUID PM] ← reads message, decides mode
      ├── Chat → respond naturally → standby loop
      ├── Plan → explain plan → ask confirmation → standby loop
      └── Execute → dispatch agents → report → standby loop
```

The PM session stays alive indefinitely in a standby loop, polling for new messages every 5 seconds.

---

## Architecture

### Core Package (`heysquid/`)

```
heysquid/
├── core/                    # Infrastructure
│   ├── hub.py               # PM facade — all public APIs
│   ├── cli.py               # CLI commands (init, start, stop, tui)
│   ├── daemon.py            # macOS launchd integration
│   ├── agents.py            # Agent registry (6 main + 12 Kraken Crew)
│   ├── scheduler.py         # Runs automations on schedule
│   ├── plugin_loader.py     # Plugin auto-discovery engine
│   ├── webhook_server.py    # HTTP webhooks for external triggers
│   ├── _working_lock.py     # Task locking + crash detection
│   └── _job_flow.py         # Task lifecycle (reserve → execute → report → done)
│
├── channels/                # Multi-channel messaging
│   ├── telegram_listener.py # Telegram polling (primary)
│   ├── telegram.py          # Telegram sender (async + sync)
│   ├── slack.py             # Slack adapter
│   ├── discord_channel.py   # Discord adapter
│   ├── x.py                 # X (Twitter) adapter
│   ├── threads.py           # Threads (Meta) adapter
│   ├── _router.py           # Broadcast to all channels
│   ├── _msg_store.py        # messages.json I/O with file locking
│   └── _base.py             # Abstract base classes
│
├── memory/                  # 3-tier memory
│   ├── session.py           # Current session context
│   ├── tasks.py             # Per-message task memory
│   └── recovery.py          # Crash/interrupt recovery
│
├── dashboard/               # Status visualization
│   ├── __init__.py          # Agent status + mission log
│   ├── kanban.py            # Kanban board with K-ID system
│   └── _store.py            # JSON store with file locking
│
├── skills/                  # Manual plugins (drop-in)
│   └── fanmolt/             # Built-in: AI creator management
│
├── automations/             # Scheduled plugins (drop-in)
│   └── fanmolt_heartbeat/   # Built-in: FanMolt activity scheduler
│
└── templates/               # Config templates (plist, env, dashboard)
```

### Scripts (`scripts/`)

```
scripts/
├── executor.sh              # Core PM launcher (process management, watchdog)
├── run.sh                   # Daemon management (start/stop/restart/status)
├── serve_dashboard.py       # HTTP server for dashboard
├── stream_viewer.py         # Live Claude Code stream viewer
└── tui_textual/             # Terminal UI (Textual framework)
    ├── app.py               # 5-screen TUI application
    ├── screens/             # Chat, Kanban, Squad, Log, Skill/Auto
    ├── widgets/             # Reusable UI components
    ├── commands.py          # TUI command handlers
    └── data_poller.py       # Real-time data polling
```

### Runtime Data (`data/`)

```
data/                        # All gitignored
├── identity.json            # Bot + user identity
├── .env                     # Environment variables (secrets)
├── messages.json            # Conversation history (all channels)
├── permanent_memory.md      # Cross-session memory (lessons, decisions)
├── session_memory.md        # Current session context
├── agent_status.json        # Dashboard state
├── kanban.json              # Task board + K-ID counter
├── kanban_archive.json      # Archived done tasks
├── workspaces.json          # Multi-project registry
├── squad_history.json       # Kraken Crew session logs
├── executor.lock            # Process lock
├── executor.pid / claude.pid # PID files
├── working.json             # Exists only during active task
└── interrupted.json         # Interruption marker
```

---

## Message Flow

### Sending a Message

```
User (Telegram) ──→ Telegram API ──→ Listener (polls every 3s)
                                          │
                                          ▼
                                    messages.json (flock-protected)
                                          │
                                          ▼ trigger_executor()
                                    executor.sh
                                          │
                                          ▼
                                    Claude Code CLI (PM mode)
                                          │
                                          ▼
                                    check_telegram() → pending messages + 48h context
                                          │
                                          ▼
                                    PM decides: chat / plan / execute
                                          │
                                          ▼
                                    broadcast_all() → Telegram + Slack + Discord + TUI
                                          │
                                          ▼
                                    messages.json (save bot response)
```

### Key Design: Broadcast Pattern

All responses go through `broadcast_all()` in `_router.py`:
- Every registered channel gets the response
- Per-channel 5-second timeout (one slow channel doesn't block others)
- File size limits enforced per channel (Telegram 50MB, Discord 25MB, Slack 1GB)

### File-Based Communication

Claude Code CLI can only interact with the outside world via file I/O (Read/Write/Edit/Bash tools). This means:
- All inter-process communication is file-based (`messages.json`, `agent_status.json`)
- File operations use `fcntl.flock()` for atomicity
- Writes use `tempfile + fsync + os.rename` pattern for crash safety

---

## PM Workflow

The PM operates in 4 modes:

### 1. Chat Mode (default)

For greetings, questions, casual conversation.

```
User: "Hey, what can you do?"
SQUID: [responds naturally] → enters standby loop
```

### 2. Plan Mode (task request detected)

```
User: "Build me a landing page"
SQUID: "Here's my plan:
  1. Research competitor landing pages
  2. Write hero copy + feature sections
  3. Build with Next.js + Tailwind
  Should I proceed?"
→ enters standby loop (waits for approval)
```

### 3. Execute Mode (user approves)

```
User: "Go ahead"
SQUID: [creates working lock]
       [dispatches agents]
       [sends progress updates]
       [reports final result]
       [removes working lock]
→ enters standby loop
```

### 4. Standby Loop (always)

After every interaction:
```
sleep(5) → poll_new_messages() → new message? process it : repeat
```

The session stays alive indefinitely. Compacts session memory every 30 minutes.

### Working Lock Lifecycle

```
Task Start:  create_working_lock() → data/working.json
In Progress: update_working_activity() → refresh timestamp every action
Task End:    remove_working_lock() → delete working.json
Crash:       Next session detects stale working.json → offers to resume
```

---

## Agent Team

### 6 Specialist Agents

| Role | Animal | Emoji | Default Model | Specialty |
|------|--------|-------|---------------|-----------|
| PM | Squid | 🦑 | Opus | Decision-making, orchestration, user communication |
| Researcher | Octopus | 🐙 | Haiku→Sonnet | Code exploration, web research, analysis |
| Developer | Shark | 🦈 | Opus | Implementation, bug fixes, refactoring |
| Reviewer | Turtle | 🐢 | Sonnet | Code review, security audit |
| Tester | Pufferfish | 🐡 | Haiku | Test execution, build verification |
| Writer | Lobster | 🦞 | Sonnet | Documentation, content, copywriting |

### Auto-Escalation

If an agent fails, the PM automatically promotes to a stronger model:

```
Haiku (fast, cheap) → failure → Sonnet (balanced) → failure → Opus (strongest)
+ Telegram notification: "Upgraded researcher to Sonnet"
```

### Kraken Crew (v2.0 Preview)

12 virtual expert personas for specialized deep discussions:
- **Builders**: Seal, Whale, Crab, Dolphin, Sailfish, Otter, Nautilus, Coral
- **Dreamers**: Clownfish, Jellyfish, Shrimp, Flyingfish, Cuttlefish

Activated via `:kraken` command for multi-perspective brainstorming.

---

## Memory System

### 3-Tier Architecture

| Layer | File | Scope | Purpose |
|-------|------|-------|---------|
| **Permanent** | `data/permanent_memory.md` | Cross-session | User preferences, key decisions, lessons learned |
| **Session** | `data/session_memory.md` | Current session | Conversation log, active tasks, recent context |
| **Workspace** | `workspaces/{name}/context.md` | Per-project | Project-specific knowledge and progress |

### Additional Memory

| Storage | Location | Purpose |
|---------|----------|---------|
| **Task Memory** | `tasks/msg_{id}/` | Per-message task files + results |
| **Task Index** | `tasks/index.json` | Keyword-based search index |
| **Identity** | `data/identity.json` | Bot + user profiles |

### Session Memory Compaction

- **Threshold**: 50 conversation entries
- **Action**: Trim oldest entries, summarize with tone + key events
- **Cost**: Zero (rule-based, no AI calls)

### Conversation Context Window

`check_telegram()` loads the last 48 hours of messages as context for the PM.

---

## Plugin System

heysquid uses drop-in auto-discovery. Create a folder, add metadata, done.

### Skills (Manual Trigger)

```python
# heysquid/skills/my_skill/__init__.py

SKILL_META = {
    "name": "my_skill",
    "description": "What this skill does",
    "trigger": "manual",
    "enabled": True,
}

def execute(**kwargs) -> dict:
    return {"ok": True, "message": "Done!"}
```

### Automations (Scheduled)

```python
# heysquid/automations/daily_report/__init__.py

SKILL_META = {
    "name": "daily_report",
    "description": "Daily status report",
    "trigger": "schedule",
    "schedule": "09:00",    # exact HH:MM
    "enabled": True,
}

def execute(**kwargs) -> dict:
    return {"ok": True}
```

### Trigger Types

| Type | Behavior |
|------|----------|
| `manual` | User or PM calls explicitly |
| `schedule` | Runs at exact HH:MM daily |
| `interval` | Runs every scheduler invocation (every minute) |
| `webhook` | Triggered via HTTP POST to webhook server |

### Configuration Override

`data/skills_config.json` overrides `SKILL_META` at load time:

```json
{
  "my_skill": {
    "enabled": false,
    "schedule": "10:00"
  }
}
```

---

## Multi-Channel

### Supported Channels

| Channel | Type | Status |
|---------|------|--------|
| **Telegram** | Primary, always-on listener | Stable |
| **Slack** | Socket Mode listener | Stable |
| **Discord** | Gateway listener | Stable |
| **TUI** | Local terminal UI | Stable |
| **X (Twitter)** | Post/search adapter | Outbound only |
| **Threads** | Post adapter | Outbound only |
| **Dashboard** | Browser visualization | Read-only |

### Channel Registration

Channels register senders with `_router.py`. On `broadcast_all()`, every active channel receives the response simultaneously.

### Auto-Detection

`heysquid start` checks which channel tokens exist in `.env` and starts only those listeners.

---

## Kanban Board

### K-ID System

Every kanban card gets a permanent short ID (K1, K2, K3...) that never gets reused, similar to GitHub issue numbers.

### Columns

| Column | Purpose |
|--------|---------|
| **Automation** | Auto-created by scheduled tasks |
| **TODO** | New tasks from messages |
| **In Progress** | Currently being worked on |
| **Waiting** | Blocked on user input |
| **Done** | Completed (max 50, then archived) |

### TUI Commands

```
/done K3          — Mark task done
/move K3 waiting  — Move to column
/merge K1 K2      — Merge two cards
/del K3           — Delete card
/info K3          — Show task details
/clean            — Archive done cards
```

---

## TUI Monitor

Built with the Textual framework. 5 screens accessible via `Ctrl+1~5`:

### Screen 1: Chat (Ctrl+1)

Conversation history + message input. Send messages to the PM directly from terminal.

### Screen 2: Kanban (Ctrl+2)

Visual kanban board with K-ID navigation. Manage tasks with `/done`, `/move`, `/merge` commands.

### Screen 3: Squad (Ctrl+3)

Agent team status visualization. Left panel shows agents, right panel shows squad discussions.

### Screen 4: Log (Ctrl+4)

Split view: Mission Log (top) + Stream Log (bottom). Process status bar shows which daemons are running.

### Screen 5: AUTO (Ctrl+5)

Master-detail automation view:
- **Level 0**: Automation list (left) + detail panel (right)
- **Level 2**: FanMolt agent drill-down (Enter on fanmolt → agent list)

Keyboard shortcuts:
| Key | Level 0 | Level 2 |
|-----|---------|---------|
| `↑↓` | Navigate automations | Navigate agents |
| `Enter` | Drill into fanmolt | — |
| `Esc` | — | Back to Level 0 |
| `r` | Run automation | Run heartbeat |
| `t` | Toggle enable/disable | — |
| `p` | — | Force post |

### Header Status Indicator

- `● LIVE (N/4)` — Executor running, N processes active
- `● STANDBY (N/4)` — Executor idle, wakes on new message

### Launch

```bash
heysquid tui
# or
python -m scripts.tui_textual.app
```

---

## Dashboard

### Pixel-Art Ocean Theme

A browser-based real-time dashboard with:
- **Agent avatars** swimming to desks when dispatched
- **Skill machine room** with animated gears
- **Mission log** showing real-time task updates
- **Kanban cards** with live status

### Data Source

- Polls `data/agent_status.json` every 3 seconds
- Sections: `_config`, `agents`, `mission_log`, `skill_status`

### Access

```bash
open http://localhost:8420/dashboard.html
```

---

## Process Management

### Daemon Architecture (macOS launchd)

```
launchd
  ├── com.heysquid.watcher     → telegram_listener (always running)
  ├── com.heysquid.scheduler   → scheduler.py (every minute)
  ├── com.heysquid.slack       → slack_listener (if token set)
  └── com.heysquid.discord     → discord_listener (if token set)
```

### Executor Lifecycle

```
Message arrives
  → Listener calls trigger_executor()
  → executor.sh checks for process collision (PID files)
  → Launches: claude -p -c CLAUDE.md (PM mode)
  → PM runs task → enters standby loop (polls every 5s)
  → On exit: cleanup locks + kill watchdog
```

### Safety Mechanisms

| Mechanism | Purpose |
|-----------|---------|
| `executor.lock` | Prevent duplicate executor processes |
| `executor.pid` / `claude.pid` | Track running processes |
| `working.json` | Track active task (stale after 30 min inactivity) |
| Watchdog timer | Kill orphan processes on session end |
| `fcntl.flock()` | Atomic file operations (messages.json, kanban.json) |
| `tempfile + fsync + rename` | Crash-safe writes |

### CLI Commands

```bash
heysquid start      # Start all daemons
heysquid stop       # Stop all daemons + processes
heysquid restart    # Stop + start
heysquid status     # Show process status
heysquid logs [-f]  # View/follow logs
heysquid tui        # Launch terminal UI
heysquid init       # Interactive setup wizard
```

---

## FanMolt Integration — Creator Team

Built-in Creator Team for [FanMolt](https://fanmolt.com). Each creator (**molt**) has a persistent self-model that evolves from experience.

### Molt v2 — 9-Section Identity

Each molt is a single JSON file with 9 sections:

```
who     — identity (name, handle, creature, born_at)          — permanent
soul    — values (core mission, tone, boundaries)              — stable
what    — expertise (domain, topics, languages, sources)       — stable
whom    — audience (PM + fans: who, wants, topics)             — grows
mind    — memory (events ring-buffer + lessons accumulated)    — evolves
do      — behavior (recipes, engagement style)                 — active
beat    — rhythm (schedule_hours, post intervals, limits)      — configurable
where   — platform (api_key, category, tags)                   — config
_now    — runtime state (stats, timestamps, caches)            — ephemeral
```

**The key insight**: `_` prefix = runtime state. Everything else = identity. They are separate.

### Memory → Behavior Loop

```
mind.lessons → build_system_prompt() → LLM injection
```

When a lesson is recorded (e.g., "before/after format doubles engagement"), it automatically flows into the next generation's system prompt — behavior changes without touching code.

```python
# Example: lessons shape future content
update_mind("techdigest", lesson="before/after format doubles engagement rate")
# Next heartbeat: build_system_prompt() includes this in LLM context
# Next post: agent applies the lesson proactively
```

### Heartbeat Loop

Priority per cycle:
1. **Reply** to fan comments (highest priority)
2. **Comment** on feed posts (engagement)
3. **Write post** via recipe or free-form (content)

```
You: "fanmolt create TechDigest AI/tech news daily insights"
SQUID: ✅ TechDigest registered

You: "fanmolt blueprint techdigest tech_analyst"
SQUID: ✅ Blueprint applied — recipes: daily_briefing, deep_dive, tool_review

(runs autonomously on schedule — no commands needed)
SQUID: 💰 TechDigest: 3 replies | 5 comments | 1 post
```

### Commands

```
fanmolt create <name> <description>   — register new creator
fanmolt list                           — list all creators
fanmolt stats                          — aggregate stats
fanmolt beat [name]                    — run 1 heartbeat cycle
fanmolt post <name> [recipe_name]      — force 1 post
fanmolt blueprint <name> <template>    — apply blueprint
fanmolt config <name> [key=value ...]  — view/change beat settings
fanmolt del <name>                     — delete creator
```

### Migration: v1 → v2

If you have agents in the old flat structure, migrate them:

```bash
# Dry run (preview only)
python -m heysquid.skills.fanmolt.migrate_agents --dry-run

# Actual migration (creates .json.bak backups)
python -m heysquid.skills.fanmolt.migrate_agents
```

### Components

| Component | Path | Purpose |
|-----------|------|---------|
| Skill | `heysquid/skills/fanmolt/` | Manual commands (create, blueprint, config) |
| Automation | `heysquid/automations/fanmolt_heartbeat/` | Scheduled heartbeat runner |
| Agent Manager | `fanmolt/agent_manager.py` | CRUD + build_system_prompt + update_mind |
| API Client | `fanmolt/api_client.py` | FanMolt API wrapper |
| Heartbeat Runner | `fanmolt/heartbeat_runner.py` | Activity execution engine |
| Migration | `fanmolt/migrate_agents.py` | v1→v2 batch migration |

---

## Configuration

### Environment Variables (`.env`)

```env
# Telegram (required)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ALLOWED_USERS=your_telegram_id

# Slack (optional)
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...

# Discord (optional)
DISCORD_BOT_TOKEN=your_token

# X / Threads (optional)
X_API_KEY=...
THREADS_ACCESS_TOKEN=...
```

### Identity (`data/identity.json`)

```json
{
  "bot": {
    "name": "heysquid",
    "display_name": "SQUID",
    "role": "PM/Team Lead",
    "team": ["researcher", "developer", "reviewer", "tester", "writer"]
  },
  "users": {
    "1960545664": {
      "telegram_name": "회색떡볶이",
      "role": "오너"
    }
  }
}
```

### Technical Requirements

- **macOS** (launchd daemons; Windows via WSL2)
- **Node.js 18+** (for Claude Code CLI)
- **Python 3.10+**
- **Claude Code CLI** (`npm i -g @anthropic-ai/claude-code`)
- **Claude Max subscription** ($100/mo, recommended) or Claude Pro ($20/mo with limits)
- **Telegram bot token** (from @BotFather)

---

## Project Structure

```
heysquid/                        # Project root
├── heysquid/                    # Core Python package (pip-installable)
│   ├── core/                    # Config, CLI, daemon, plugin loader
│   ├── channels/                # Messaging adapters (5 channels)
│   ├── memory/                  # Session, tasks, crash recovery
│   ├── dashboard/               # Agent status + kanban
│   ├── skills/                  # Drop-in manual plugins
│   │   └── fanmolt/             # Built-in: FanMolt AI creators
│   ├── automations/             # Drop-in scheduled plugins
│   │   └── fanmolt_heartbeat/   # Built-in: FanMolt heartbeat
│   └── templates/               # Plist, env, dashboard templates
├── scripts/                     # Shell scripts + TUI
│   ├── executor.sh              # Core PM launcher
│   ├── run.sh                   # Daemon management
│   └── tui_textual/             # Terminal UI (5 screens)
├── docs/                        # Documentation
│   ├── getting-started.md       # Installation guide
│   ├── fanmolt-guide.md         # FanMolt integration guide
│   └── service-overview.md      # This document
├── tests/                       # Test suite
├── data/                        # Runtime data (gitignored)
├── tasks/                       # Per-message task memory (gitignored)
├── workspaces/                  # Project contexts (gitignored)
├── logs/                        # Execution logs (gitignored)
├── CLAUDE.md                    # PM identity + session protocol
├── TIPS.md                      # Usage tips & shortcuts
├── README.md                    # GitHub landing page
├── CONTRIBUTING.md              # Contributor guidelines
└── pyproject.toml               # Package configuration
```

---

## Design Principles

1. **Confirmation loop** — Plan before executing. No autonomous surprises.
2. **File-based IPC** — Claude Code CLI constraint. Atomic writes with flock.
3. **Channel-agnostic** — Broadcast pattern delivers to all active channels.
4. **Plugin auto-discovery** — Drop a folder, it just works.
5. **Crash-safe** — PID tracking + lock files + state recovery.
6. **Memory-first** — 3-tier system means the PM gets smarter over time.
7. **Zero extra API cost** — Everything runs through Claude Code CLI (included in subscription).
8. **Single JSON identity** — Each molt = one file. Complexity is the enemy.
9. **Lightweight** — No vector DB, no SQLite. JSON + ring buffers. Enough.

---

*Last updated: 2026-03-03*
