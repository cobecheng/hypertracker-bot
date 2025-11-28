# Deployment Instructions

## Overview

This repository includes everything you need to deploy HyperTracker Bot to AWS Free Tier.

## Files

- **[AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)** - Complete step-by-step deployment guide (10 parts)
- **[QUICK_START.md](QUICK_START.md)** - Quick reference for deployment
- **[ecosystem.config.js](ecosystem.config.js)** - PM2 process manager configuration
- **[deploy.sh](deploy.sh)** - Automated deployment script for EC2
- **[update.sh](update.sh)** - Script to update bot from GitHub
- **[setup_swap.sh](setup_swap.sh)** - Script to add swap memory (recommended for t2.micro)

## Quick Deploy

### Option 1: Automated (Recommended)
```bash
# On your EC2 server
curl -sSL https://raw.githubusercontent.com/cobecheng/hypertracker-bot/main/deploy.sh | bash
```

### Option 2: Manual
```bash
# On your EC2 server
git clone https://github.com/cobecheng/hypertracker-bot.git
cd hypertracker-bot
chmod +x deploy.sh
./deploy.sh
```

Then:
```bash
nano .env  # Add your BOT_TOKEN
pm2 start ecosystem.config.js
pm2 save
```

## Documentation

For complete instructions, see [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)

## What You Need

1. **AWS Account** - Sign up at https://aws.amazon.com/free/
2. **Telegram Bot Token** - Get from [@BotFather](https://t.me/botfather)
3. **GitHub Account** - Code hosted at https://github.com/cobecheng/hypertracker-bot

## Cost

AWS Free Tier includes:
- ✅ 750 hours/month of t2.micro (enough for 24/7)
- ✅ 30 GB storage
- ✅ FREE for 12 months

After 12 months: ~$8-10/month

## Support

- Full Guide: [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)
- Quick Reference: [QUICK_START.md](QUICK_START.md)
- Issues: https://github.com/cobecheng/hypertracker-bot/issues
