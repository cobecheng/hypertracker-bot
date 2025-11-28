#!/bin/bash

# HyperTracker Bot Update Script
# Use this to pull latest changes from GitHub and restart the bot

set -e

echo "=================================="
echo "Updating HyperTracker Bot"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Navigate to project directory
cd ~/hypertracker-bot || { echo "Error: Project directory not found"; exit 1; }

# Pull latest changes
echo -e "${GREEN}[1/4] Pulling latest changes from GitHub...${NC}"
git pull origin main

# Activate virtual environment and update dependencies
echo -e "${GREEN}[2/4] Updating Python dependencies...${NC}"
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Check if .env needs updates (compare with .env.example)
echo -e "${GREEN}[3/4] Checking environment configuration...${NC}"
if [ -f ".env.example" ] && [ -f ".env" ]; then
    echo "Environment file exists. Check for new variables in .env.example"
fi

# Restart bot with PM2
echo -e "${GREEN}[4/4] Restarting bot...${NC}"
pm2 restart hypertracker-bot || pm2 start ecosystem.config.js

echo ""
echo -e "${GREEN}=================================="
echo "Update Complete!"
echo "==================================${NC}"
echo ""
echo "Check status: pm2 status"
echo "View logs: pm2 logs hypertracker-bot"
echo ""
