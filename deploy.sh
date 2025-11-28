#!/bin/bash

# HyperTracker Bot Deployment Script for AWS EC2
# This script automates the initial deployment on a fresh Ubuntu EC2 instance

set -e  # Exit on any error

echo "=================================="
echo "HyperTracker Bot Deployment Script"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as ubuntu user
if [ "$USER" != "ubuntu" ]; then
    echo -e "${YELLOW}Warning: This script is designed to run as 'ubuntu' user on EC2${NC}"
fi

# Update system
echo -e "${GREEN}[1/8] Updating system packages...${NC}"
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
echo -e "${GREEN}[2/8] Installing Python 3.11...${NC}"
sudo apt install python3.11 python3.11-venv python3-pip -y
sudo apt install build-essential libssl-dev libffi-dev python3.11-dev -y

# Install Git
echo -e "${GREEN}[3/8] Installing Git...${NC}"
sudo apt install git sqlite3 -y

# Clone repository (if not already in the directory)
if [ ! -d ".git" ]; then
    echo -e "${GREEN}[4/8] Cloning repository...${NC}"
    cd ~
    git clone https://github.com/cobecheng/hypertracker-bot.git
    cd hypertracker-bot
else
    echo -e "${GREEN}[4/8] Already in repository directory${NC}"
fi

# Create virtual environment
echo -e "${GREEN}[5/8] Setting up Python virtual environment...${NC}"
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo -e "${GREEN}[6/8] Installing Python dependencies...${NC}"
pip install --upgrade pip
pip install -r requirements.txt

# Set up environment file
if [ ! -f ".env" ]; then
    echo -e "${GREEN}[7/8] Creating .env file...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}IMPORTANT: Edit .env file and add your BOT_TOKEN${NC}"
    echo -e "${YELLOW}Run: nano .env${NC}"
else
    echo -e "${GREEN}[7/8] .env file already exists${NC}"
fi

# Install Node.js and PM2
echo -e "${GREEN}[8/8] Installing Node.js and PM2...${NC}"
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
sudo npm install -g pm2

# Create logs directory
mkdir -p logs

echo ""
echo -e "${GREEN}=================================="
echo "Deployment Complete!"
echo "==================================${NC}"
echo ""
echo "Next steps:"
echo "1. Edit .env file: nano .env"
echo "2. Add your BOT_TOKEN from @BotFather"
echo "3. Start the bot: pm2 start ecosystem.config.js"
echo "4. Save PM2 process: pm2 save"
echo "5. Set up autostart: pm2 startup systemd"
echo ""
echo "Useful commands:"
echo "  pm2 status          - Check bot status"
echo "  pm2 logs            - View logs"
echo "  pm2 restart all     - Restart bot"
echo ""
