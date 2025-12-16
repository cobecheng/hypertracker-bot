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

You have **three options** for running both services together:

### Option A: Using Shell Scripts (Recommended for Simple Deployment)

```bash
# Install screen
sudo apt install screen -y

# Start both services
./start_all.sh

# View bot logs
screen -r hypertracker-bot

# View webhook logs
screen -r hypertracker-webhook

# Detach from screen (keep running): Ctrl+A then D

# Stop all services
./stop_all.sh
```

### Option B: Using PM2 (Recommended for Production)

#### 6B.1 Install PM2 (Process Manager)

```bash
# Install Node.js (required for PM2)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2 globally
sudo npm install -g pm2
```

#### 6B.2 Create PM2 Ecosystem File

```bash
# Still in the hypertracker-bot directory
nano ecosystem.config.js
```

**Paste this content**:

```javascript
module.exports = {
  apps: [
    {
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
      error_file: './logs/bot-err.log',
      out_file: './logs/bot-out.log',
      time: true
    },
    {
      name: 'hypertracker-webhook',
      script: 'venv/bin/python',
      args: 'alchemy_webhook_server.py',
      cwd: '/home/ubuntu/hypertracker-bot',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '300M',
      env: {
        NODE_ENV: 'production'
      },
      error_file: './logs/webhook-err.log',
      out_file: './logs/webhook-out.log',
      time: true
    }
  ]
};
```

**Save and exit**: `Ctrl+X`, `Y`, `Enter`

#### 6B.3 Start Both Services with PM2

```bash
# Create logs directory
mkdir -p logs

# Start both services
pm2 start ecosystem.config.js

# Check status
pm2 status

# View bot logs (real-time)
pm2 logs hypertracker-bot

# View webhook logs (real-time)
pm2 logs hypertracker-webhook

# View all logs
pm2 logs

# Stop logs view: Ctrl+C
```

#### 6B.4 Set PM2 to Start on Boot

```bash
# Generate startup script
pm2 startup systemd

# This will show a command to run - copy and run it
# It will look like:
# sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u ubuntu --hp /home/ubuntu

# Save current PM2 process list
pm2 save
```

### Option C: Using Systemd (Most Robust for Production)

Create systemd services for each process:

#### 6C.1 Create Bot Service

```bash
sudo nano /etc/systemd/system/hypertracker-bot.service
```

Add:
```ini
[Unit]
Description=HyperTracker Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hypertracker-bot
Environment="PATH=/home/ubuntu/hypertracker-bot/venv/bin"
ExecStart=/home/ubuntu/hypertracker-bot/venv/bin/python /home/ubuntu/hypertracker-bot/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 6C.2 Create Webhook Service

```bash
sudo nano /etc/systemd/system/hypertracker-webhook.service
```

Add:
```ini
[Unit]
Description=HyperTracker Alchemy Webhook Server
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hypertracker-bot
Environment="PATH=/home/ubuntu/hypertracker-bot/venv/bin"
ExecStart=/home/ubuntu/hypertracker-bot/venv/bin/python /home/ubuntu/hypertracker-bot/alchemy_webhook_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### 6C.3 Enable and Start Services

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable (auto-start on boot)
sudo systemctl enable hypertracker-bot
sudo systemctl enable hypertracker-webhook

# Start services
sudo systemctl start hypertracker-bot
sudo systemctl start hypertracker-webhook

# Check status
sudo systemctl status hypertracker-bot
sudo systemctl status hypertracker-webhook
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

## Part 8: Alchemy Webhook Setup (EVM Transaction Tracking)

### 8.1 Update AWS Security Group

Before configuring Alchemy webhooks, you need to allow incoming HTTP traffic on port 8080:

1. **Go to EC2 Console** → Security Groups
2. **Select your instance's security group**
3. **Edit inbound rules** → Add rule:
   - Type: Custom TCP
   - Port: 8080
   - Source: 0.0.0.0/0 (anywhere)
   - Description: Alchemy webhook

### 8.2 Get Your Webhook URL

Your webhook URL is:
```
http://YOUR_EC2_PUBLIC_IP:8080/alchemy-webhook
```

**Example:**
```
http://54.123.45.67:8080/alchemy-webhook
```

Find your EC2 public IP in the EC2 console.

### 8.3 Configure Alchemy Webhook

1. **Go to** [Alchemy Dashboard](https://dashboard.alchemy.com/)
2. **Select or create your app** (choose the network: Ethereum, Base, Arbitrum, etc.)
3. **Navigate to** "Notify" → "Webhooks"
4. **Click "Create Webhook"**

**Webhook Configuration:**
- **Webhook Type:** Address Activity
- **Webhook URL:** `http://YOUR_EC2_IP:8080/alchemy-webhook`
- **Network:** Choose your network (Ethereum Mainnet, Base, etc.)
- **Addresses to Track:**
  - Add the EVM addresses you want to monitor
  - You can add addresses later via the bot's "EVM txn tracking" menu

**Events to Subscribe:**
- ✅ External transfers
- ✅ Internal transfers
- ✅ Token transfers (ERC-20)
- ✅ NFT transfers (optional)

5. **Enable Signature Verification** (recommended for security)
6. **Copy the signing key** and add to your `.env`:

```bash
# On your EC2 instance
cd ~/hypertracker-bot
nano .env
```

Add:
```env
ALCHEMY_API_KEY=your_alchemy_api_key
ALCHEMY_WEBHOOK_SIGNING_KEY=your_signing_key_from_alchemy
```

7. **Restart the webhook server:**

```bash
# If using PM2:
pm2 restart hypertracker-webhook

# If using systemd:
sudo systemctl restart hypertracker-webhook

# If using screen:
./stop_all.sh && ./start_all.sh
```

### 8.4 Test the Webhook

1. **Test from Alchemy Dashboard:**
   - Use Alchemy's "Test Webhook" feature
   - Send a test event

2. **Check webhook server logs:**
```bash
# PM2:
pm2 logs hypertracker-webhook

# Systemd:
sudo journalctl -u hypertracker-webhook -f

# Screen:
screen -r hypertracker-webhook
```

3. **Test endpoint health:**
```bash
curl http://YOUR_EC2_IP:8080/health
```

Should return: `{"status":"healthy"}`

### 8.5 Add Addresses to Track via Telegram

1. Open your bot on Telegram
2. Click "🔷 EVM txn tracking"
3. Click "➕ Add EVM Address"
4. Send the address you want to track
5. Provide a label

The bot will now send you notifications when transactions occur on that address!

## Part 9: Security Best Practices

### 9.1 Restrict SSH Access

1. Go to EC2 Console > Security Groups
2. Select your instance's security group
3. Edit inbound rules:
   - **SSH (22)**: Change to "My IP" instead of "Anywhere"
   - Keep port 8080 open for Alchemy webhooks

### 9.2 Set Up Automatic Updates

```bash
# Install unattended upgrades
sudo apt install unattended-upgrades -y

# Enable automatic security updates
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 9.3 Create Swap File (Optional - helps with low memory)

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
