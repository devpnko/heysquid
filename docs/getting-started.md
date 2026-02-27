# Getting Started

A step-by-step guide to setting up heysquid from scratch.

## What You'll Need

| Requirement | Why | Cost |
|-------------|-----|------|
| **macOS** | heysquid uses launchd for daemon management | — |
| **Python 3.10+** | Runtime | Free |
| **Claude Code CLI** | The brain — all AI work runs through Claude Code | Free (CLI) |
| **Claude Max subscription** | Unlimited Claude usage for your PM and agents | $100/mo |
| **Telegram bot token** | Primary communication channel | Free |

> **Claude Pro ($20/mo)** also works but has daily usage limits. Claude Max is recommended for always-on operation.

## Step 1: Install Claude Code

If you haven't already:

```bash
# macOS
brew install claude-code

# Or via npm
npm install -g @anthropic-ai/claude-code
```

Verify it works:
```bash
claude --version
```

## Step 2: Install heysquid

```bash
pip install heysquid
```

Or with all optional channels:
```bash
pip install 'heysquid[all]'    # Telegram + Slack + Discord + TUI
```

Verify:
```bash
heysquid --help
```

## Step 3: Create a Telegram Bot

1. Open Telegram and message [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Choose a name (e.g., "My SQUID")
4. Choose a username (e.g., `my_squid_bot`)
5. Copy the **bot token** (looks like `123456:ABC-DEF...`)

Then get your Telegram user ID:
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy the **user ID** number

## Step 4: Initialize heysquid

```bash
heysquid init
```

The interactive wizard will ask for:
- Telegram bot token (paste from Step 3)
- Telegram user ID (paste from Step 3)
- Slack/Discord tokens (optional — press Enter to skip)

This creates:
- `data/` directory with `.env`, identity, and memory files
- Daemon configuration templates
- Empty workspace directories

## Step 5: Start the Daemon

```bash
heysquid start
```

You should see:
```
✅ Watcher daemon started
✅ Scheduler daemon started
```

Verify everything is running:
```bash
heysquid status
```

## Step 6: Send Your First Message

Open Telegram and send a message to your bot:

```
Hello!
```

Within 10 seconds, SQUID should respond. You now have a personal PM agent.

## Step 7: Try Some Commands

```
# Ask SQUID to do something
"Check the weather in Seoul"

# Create a FanMolt AI creator
"fanmolt create TechDigest AI tech news for builders"

# Check status
"fanmolt list"

# Launch the terminal UI
```

From your terminal:
```bash
heysquid tui
```

## What's Next

- **[FanMolt Guide](fanmolt-guide.md)** — Set up AI creators that auto-post and earn revenue
- **[Plugin Guide](../heysquid/skills/GUIDE.md)** — Create your own skills and automations
- **[Contributing](../CONTRIBUTING.md)** — Help improve heysquid

## Common Issues

### "heysquid: command not found"

Make sure pip installed to a directory in your PATH:
```bash
python3 -m heysquid.core.cli --help
```

Or add pip's bin directory to PATH:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

### Bot doesn't respond

1. Check daemon status: `heysquid status`
2. Check logs: `heysquid logs -f`
3. Verify the Telegram token is correct in `data/.env`
4. Make sure your user ID is in `TELEGRAM_ALLOWED_USERS`

### "Claude CLI not found"

The executor needs Claude Code CLI in PATH. Install it and verify:
```bash
which claude
claude --version
```

### Daemon won't start

On macOS, launchd requires the plist files to be valid. Check:
```bash
heysquid logs
```

If you see permission errors, make sure the scripts are executable:
```bash
chmod +x scripts/executor.sh
```
