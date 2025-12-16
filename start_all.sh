#!/bin/bash
# Simple shell script to run both services using screen or tmux
# Usage: ./start_all.sh

echo "=========================================="
echo "HyperTracker Bot - Starting All Services"
echo "=========================================="
echo ""

# Check if running in virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate || {
        echo "Error: Virtual environment not found. Run: python -m venv venv"
        exit 1
    }
fi

# Check if screen or tmux is available
if command -v screen &> /dev/null; then
    echo "Using screen to manage processes..."
    echo ""

    # Kill existing sessions if any
    screen -S hypertracker-bot -X quit 2>/dev/null
    screen -S hypertracker-webhook -X quit 2>/dev/null

    # Start bot in detached screen
    echo "Starting Telegram Bot..."
    screen -dmS hypertracker-bot python run.py

    # Wait a moment
    sleep 2

    # Start webhook server in detached screen
    echo "Starting Webhook Server..."
    screen -dmS hypertracker-webhook python alchemy_webhook_server.py

    echo ""
    echo "✅ Both services started!"
    echo ""
    echo "To view logs:"
    echo "  Bot:     screen -r hypertracker-bot"
    echo "  Webhook: screen -r hypertracker-webhook"
    echo ""
    echo "To detach: Press Ctrl+A then D"
    echo "To stop all:"
    echo "  ./stop_all.sh"
    echo "  or: screen -S hypertracker-bot -X quit && screen -S hypertracker-webhook -X quit"

elif command -v tmux &> /dev/null; then
    echo "Using tmux to manage processes..."
    echo ""

    # Kill existing session if any
    tmux kill-session -t hypertracker 2>/dev/null

    # Create new session
    tmux new-session -d -s hypertracker -n bot "python run.py"
    tmux new-window -t hypertracker -n webhook "python alchemy_webhook_server.py"

    echo ""
    echo "✅ Both services started in tmux!"
    echo ""
    echo "To attach: tmux attach -t hypertracker"
    echo "To switch windows: Ctrl+B then 0 (bot) or 1 (webhook)"
    echo "To detach: Ctrl+B then D"
    echo "To stop all: tmux kill-session -t hypertracker"

else
    echo "⚠️  Neither screen nor tmux found."
    echo "Using Python process manager instead..."
    echo ""
    python start_all.py
fi
