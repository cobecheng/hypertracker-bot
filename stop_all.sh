#!/bin/bash
# Stop all HyperTracker services
# Usage: ./stop_all.sh

echo "Stopping HyperTracker Bot services..."

# Stop screen sessions
if command -v screen &> /dev/null; then
    screen -S hypertracker-bot -X quit 2>/dev/null && echo "✓ Bot stopped"
    screen -S hypertracker-webhook -X quit 2>/dev/null && echo "✓ Webhook server stopped"
fi

# Stop tmux session
if command -v tmux &> /dev/null; then
    tmux kill-session -t hypertracker 2>/dev/null && echo "✓ Tmux session stopped"
fi

# Kill any remaining Python processes
pkill -f "python.*run.py" 2>/dev/null
pkill -f "python.*alchemy_webhook_server.py" 2>/dev/null

echo "All services stopped"
