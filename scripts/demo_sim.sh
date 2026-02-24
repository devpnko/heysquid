#!/bin/bash
# Demo simulation script for VHS recording
# Simulates heysquid CLI output without actually running daemons

CMD="${1:-help}"

case "$CMD" in
    version)
        echo "heysquid 0.1.0"
        ;;
    init)
        echo "heysquid init"
        echo "========================================"
        echo ""
        echo "[1/7] Environment check..."
        echo "  Python: 3.12.7"
        echo "  Claude CLI: /usr/local/bin/claude"
        echo ""
        echo "[2/7] Creating directories..."
        echo "  data/"
        echo "  tasks/"
        echo "  workspaces/"
        echo "  logs/"
        echo ""
        echo "[3/7] Telegram bot token"
        echo "  Create a bot via @BotFather on Telegram and paste the token."
        sleep 0.5
        echo "  [OK] Saved"
        echo ""
        echo "[4/7] Telegram user ID"
        sleep 0.3
        echo "  [OK] Saved"
        echo ""
        echo "[5/7] Slack integration (optional)"
        echo "  [SKIP] Add Slack anytime by editing .env"
        echo ""
        echo "[6/7] Discord integration (optional)"
        echo "  [SKIP] Add Discord anytime by editing .env"
        echo ""
        echo "[7/7] Setup complete!"
        echo ""
        echo "Next steps:"
        echo "  1. Review .env"
        echo "  2. Start daemon: heysquid start"
        echo "  3. Check status: heysquid status"
        echo ""
        echo "Optional:"
        echo "  pip install 'heysquid[slack]'     # Add Slack support"
        echo "  pip install 'heysquid[discord]'   # Add Discord support"
        echo "  pip install 'heysquid[all]'       # Install everything"
        ;;
    start)
        echo "heysquid daemon starting..."
        echo ""
        echo "  [watcher]   Installed + loaded"
        echo "  [scheduler] Installed + loaded"
        echo "  [slack]     Skipped (no SLACK_BOT_TOKEN)"
        echo "  [discord]   Skipped (no DISCORD_BOT_TOKEN)"
        echo ""
        echo "Daemon started. Send a message to your Telegram bot!"
        ;;
    status)
        echo "heysquid status"
        echo "========================================"
        echo ""
        echo "Services:"
        printf "  %-14s %s\n" "[watcher]" "● running (PID 48291)"
        printf "  %-14s %s\n" "[scheduler]" "● running (PID 48305)"
        printf "  %-14s %s\n" "[slack]" "○ not configured"
        printf "  %-14s %s\n" "[discord]" "○ not configured"
        echo ""
        echo "Processes:"
        echo "  Claude PM:   ● active (PID 48392, uptime 2h 31m)"
        echo "  Executor:    ○ idle"
        echo ""
        echo "Lock files:"
        echo "  executor.lock: ● present (session active)"
        echo "  working.json:  ○ none (standby)"
        echo ""
        echo "Memory:"
        echo "  permanent_memory.md: 47 lines"
        echo "  session_memory.md:   23 lines"
        ;;
    conversation)
        # Simulated Telegram conversation flow
        echo ""
        printf "\033[36m━━━ Telegram ━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n"
        echo ""
        sleep 0.5
        printf "\033[33m 👤 You:\033[0m  Make a landing page for my new app\n"
        sleep 1.5
        printf "\033[35m 🦑 SQUID:\033[0m Got it! Here's my plan:\n"
        sleep 0.5
        echo "         - React + Tailwind responsive page"
        echo "         - Hero, features, pricing, CTA sections"
        echo "         - Mobile-first design"
        echo "         Shall I proceed?"
        sleep 1.5
        printf "\033[33m 👤 You:\033[0m  Yes, go ahead\n"
        sleep 1
        printf "\033[35m 🦑 SQUID:\033[0m On it! Dispatching 🦈developer...\n"
        sleep 2
        printf "\033[35m 🦑 SQUID:\033[0m Progress: components done, styling...\n"
        sleep 2
        printf "\033[35m 🦑 SQUID:\033[0m Done! Landing page created:\n"
        echo "         → src/pages/Landing.tsx (247 lines)"
        echo "         → src/styles/landing.css"
        echo "         Deployed to localhost:3000"
        sleep 1
        printf "\033[33m 👤 You:\033[0m  Add a dark mode toggle\n"
        sleep 1
        printf "\033[35m 🦑 SQUID:\033[0m Adding dark mode... 🦈developer on it.\n"
        sleep 1.5
        printf "\033[35m 🦑 SQUID:\033[0m Done! Dark mode toggle added ✓\n"
        echo ""
        printf "\033[36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m\n"
        ;;
esac
