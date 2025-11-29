# AWS Free Tier Deployment Guide

This guide will walk you through deploying HyperTracker Bot from GitHub to AWS EC2 Free Tier.

## Prerequisites

- GitHub account with your repository: `https://github.com/cobecheng/hypertracker-bot.git`
- AWS account (sign up at https://aws.amazon.com/free/)
- Telegram Bot Token from [@BotFather](https://t.me/botfather)

## Part 1: Push Your Code to GitHub

### 1.1 Authenticate with GitHub (if not already done)

```bash
# Option 1: Using web authentication (RECOMMENDED)
gh auth login --web --git-protocol https

# Option 2: Using SSH
gh auth login --git-protocol ssh
```

### 1.2 Ensure All Code is Committed

```bash
# Check status
git status

# Add any untracked files
git add .

# Commit changes
git commit -m "Prepare for AWS deployment"

# Push to GitHub
git push origin main
```

### 1.3 Verify on GitHub

Visit: https://github.com/cobecheng/hypertracker-bot

## Part 2: Set Up AWS EC2 Instance

### 2.1 Sign in to AWS Console

1. Go to https://console.aws.amazon.com/
2. Navigate to EC2 Dashboard
3. Click "Launch Instance"

### 2.2 Configure Instance

**Name**: `hypertracker-bot`

**Application and OS Images (Amazon Machine Image)**:
- Choose: **Ubuntu Server 24.04 LTS** (Free tier eligible)
- Architecture: 64-bit (x86)

**Instance Type**:
- Choose: **t2.micro** (Free tier eligible - 1 vCPU, 1 GB RAM)

**Key Pair**:
- Click "Create new key pair"
- Name: `hypertracker-bot-key`
- Key pair type: RSA
- Private key format: `.pem` (for Mac/Linux) or `.ppk` (for Windows/PuTTY)
- **Download and save the key file securely** - you'll need it to SSH

**Network Settings**:
- Create security group with:
  - SSH (port 22) - Your IP only (for security)
  - HTTPS (port 443) - Optional, for future webhooks

**Configure Storage**:
- 8 GB gp3 (Free tier eligible up to 30 GB)

**Advanced Details** (optional):
- Enable "Detailed CloudWatch monitoring" if you want extra monitoring

Click **Launch Instance**

### 2.3 Wait for Instance to Start

- Wait for "Instance State" to show "Running"
- Note the **Public IPv4 address** (you'll need this)

## Part 3: Connect to Your EC2 Instance

### 3.1 Set Key Permissions (Mac/Linux)

```bash
# Navigate to where you downloaded the key
cd ~/Downloads

# Set correct permissions
chmod 400 hypertracker-bot-key.pem
```

### 3.2 SSH into Instance

```bash
# Replace <YOUR-PUBLIC-IP> with your instance's public IP
ssh -i hypertracker-bot-key.pem ubuntu@<YOUR-PUBLIC-IP>

# Example:
# ssh -i hypertracker-bot-key.pem ubuntu@54.123.45.67
```

**For Windows**: Use PuTTY with your `.ppk` key file

## Part 4: Set Up the Server

### 4.1 Update System

```bash
sudo apt update && sudo apt upgrade -y
```

### 4.2 Install Python 3.11+

```bash
# Install Python 3.11 and pip
sudo apt install python3.12 python3.12-venv python3-pip -y

# Verify installation
python3.12 --version
```

### 4.3 Install Git

```bash
sudo apt install git -y
git --version
```

### 4.4 Install Additional Dependencies

```bash
# Install SQLite (usually pre-installed)
sudo apt install sqlite3 -y

# Install system dependencies for Python packages
sudo apt install build-essential libssl-dev libffi-dev python3.12-dev -y
```

## Part 5: Deploy Your Bot

### 5.1 Clone Repository

```bash
# Clone your repository
git clone https://github.com/cobecheng/hypertracker-bot.git

# Navigate into the directory
cd hypertracker-bot
```

### 5.2 Set Up Python Environment

```bash
# Create virtual environment
python3.12 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 5.3 Configure Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit .env file
nano .env
```

**Update the following**:
- `BOT_TOKEN=` - Your actual Telegram bot token from BotFather
- Leave other settings at defaults

**Save and exit**: Press `Ctrl+X`, then `Y`, then `Enter`

### 5.4 Test the Bot

```bash
# Test run
python run.py
```

If you see "Bot started successfully" - it's working! Press `Ctrl+C` to stop.

## Part 6: Keep Bot Running 24/7

### 6.1 Install PM2 (Process Manager)

```bash
# Install Node.js (required for PM2)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
sudo npm install -g pm2
```

### 6.2 Create PM2 Ecosystem File

```bash
# Still in the hypertracker-bot directory
nano ecosystem.config.js
```

**Paste this content**:

```javascript
module.exports = {
  apps: [{
    name: 'hypertracker-bot',
    script: 'venv/bin/python',
    args: 'run.py',
    cwd: '/home/ubuntu/hypertracker-bot',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '500M',
    env: {
      NODE_ENV: 'production'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_file: './logs/combined.log',
    time: true
  }]
};
```

**Save and exit**: `Ctrl+X`, `Y`, `Enter`

### 6.3 Start Bot with PM2

```bash
# Create logs directory
mkdir -p logs

# Start the bot
pm2 start ecosystem.config.js

# Check status
pm2 status

# View logs (real-time)
pm2 logs hypertracker-bot

# Stop logs view: Ctrl+C
```

### 6.4 Set PM2 to Start on Boot

```bash
# Generate startup script
pm2 startup systemd

# This will show a command to run - copy and run it
# It will look like:
# sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u ubuntu --hp /home/ubuntu

# Save current PM2 process list
pm2 save
```

## Part 7: Managing Your Bot

### Useful PM2 Commands

```bash
# View status
pm2 status

# View logs
pm2 logs hypertracker-bot

# Restart bot
pm2 restart hypertracker-bot

# Stop bot
pm2 stop hypertracker-bot

# Start bot
pm2 start hypertracker-bot

# View detailed info
pm2 info hypertracker-bot

# Monitor resources
pm2 monit
```

### Updating Your Bot

```bash
# SSH into your server
ssh -i hypertracker-bot-key.pem ubuntu@<YOUR-PUBLIC-IP>

# Navigate to directory
cd hypertracker-bot

# Pull latest changes
git pull origin main

# Activate virtual environment
source venv/bin/activate

# Update dependencies (if changed)
pip install -r requirements.txt

# Restart bot
pm2 restart hypertracker-bot
```

### Viewing Database

```bash
cd ~/hypertracker-bot

# Open database
sqlite3 data/hypertracker.db

# View tables
.tables

# View users
SELECT * FROM users;

# Exit
.quit
```

## Part 8: Security Best Practices

### 8.1 Update Security Group

1. Go to EC2 Console > Security Groups
2. Select your instance's security group
3. Edit inbound rules:
   - **SSH (22)**: Change to "My IP" instead of "Anywhere"
   - Remove any unnecessary ports

### 8.2 Set Up Automatic Updates

```bash
# Install unattended upgrades
sudo apt install unattended-upgrades -y

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 8.3 Create Swap File (Optional - helps with low memory)

```bash
# Create 1GB swap file
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## Part 9: Monitoring & Troubleshooting

### Check Bot Status

```bash
pm2 status
```

### View Real-time Logs

```bash
pm2 logs hypertracker-bot --lines 100
```

### Check System Resources

```bash
# Memory usage
free -h

# Disk usage
df -h

# CPU and processes
htop
# (Install with: sudo apt install htop -y)
```

### Common Issues

**Issue**: Bot keeps restarting
- Check logs: `pm2 logs hypertracker-bot`
- Verify `.env` file has correct `BOT_TOKEN`
- Check memory: `free -h` (consider adding swap)

**Issue**: Can't SSH into instance
- Verify security group allows SSH from your IP
- Check instance is running
- Verify key file permissions: `chmod 400 hypertracker-bot-key.pem`

**Issue**: Out of memory
- Add swap file (see Section 8.3)
- Consider upgrading instance type (will cost money)

**Issue**: Database locked errors
- Ensure only one instance is running: `pm2 status`
- Restart bot: `pm2 restart hypertracker-bot`

## Part 10: Cost Optimization

### AWS Free Tier Limits (12 months)
- ✅ 750 hours/month of t2.micro instance (enough for 24/7 operation)
- ✅ 30 GB of EBS storage
- ✅ 15 GB of bandwidth out per month

### Staying Within Free Tier
1. **Use only one t2.micro instance**
2. **Monitor your usage**: AWS Console > Billing Dashboard
3. **Set up billing alerts**: Receive email if charges exceed $0
4. **Stop instance when testing**: Don't run multiple instances
5. **Keep storage under 30 GB**: Monitor with `df -h`

### After 12 Months
- t2.micro costs ~$8-10/month
- Consider alternatives: DigitalOcean ($4/month), Oracle Cloud (always free tier)

## Quick Reference

### Server Details
- **SSH Command**: `ssh -i hypertracker-bot-key.pem ubuntu@<YOUR-IP>`
- **Project Directory**: `/home/ubuntu/hypertracker-bot`
- **Database Path**: `/home/ubuntu/hypertracker-bot/data/hypertracker.db`
- **Log Files**: `/home/ubuntu/hypertracker-bot/logs/`

### Essential Commands
```bash
# Connect to server
ssh -i hypertracker-bot-key.pem ubuntu@<YOUR-IP>

# Check bot status
pm2 status

# View logs
pm2 logs hypertracker-bot

# Restart bot
pm2 restart hypertracker-bot

# Update code
cd ~/hypertracker-bot && git pull && pm2 restart hypertracker-bot
```

## Support

If you encounter issues:
1. Check PM2 logs: `pm2 logs hypertracker-bot`
2. Check system logs: `journalctl -xe`
3. Verify environment variables: `cat .env`
4. Test manually: `source venv/bin/activate && python run.py`

## Next Steps

Once deployed:
1. Test by sending `/start` to your bot on Telegram
2. Add a wallet address to monitor
3. Monitor logs to ensure everything works
4. Set up billing alerts in AWS Console
5. Consider adding CloudWatch monitoring for advanced metrics

Your bot is now running 24/7 on AWS Free Tier! 🚀
