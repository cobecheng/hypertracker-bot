# Quick Start - AWS Deployment

## Step-by-Step Summary

### 1. Push to GitHub
```bash
git add .
git commit -m "Ready for AWS deployment"
git push origin main
```

### 2. Create AWS EC2 Instance
- Go to [AWS Console](https://console.aws.amazon.com/)
- Launch EC2 instance:
  - **AMI**: Ubuntu Server 24.04 LTS
  - **Type**: t2.micro (Free Tier)
  - **Key Pair**: Create and download `hypertracker-bot-key.pem`
  - **Storage**: 8 GB
- Wait for instance to start, note the **Public IP**

### 3. Connect to Server
```bash
# Mac/Linux
chmod 400 hypertracker-bot-key.pem
ssh -i hypertracker-bot-key.pem ubuntu@YOUR-PUBLIC-IP
```

### 4. Deploy Bot (One Command!)
```bash
# On the EC2 server
curl -sSL https://raw.githubusercontent.com/cobecheng/hypertracker-bot/main/deploy.sh | bash
```

Or manually:
```bash
git clone https://github.com/cobecheng/hypertracker-bot.git
cd hypertracker-bot
./deploy.sh
```

### 5. Configure Bot
```bash
nano .env
# Add your BOT_TOKEN, save with Ctrl+X, Y, Enter
```

### 6. Start Bot
```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup systemd  # Run the command it outputs
```

### 7. Verify
```bash
pm2 status
pm2 logs hypertracker-bot
```

## Daily Commands

```bash
# SSH into server
ssh -i hypertracker-bot-key.pem ubuntu@YOUR-IP

# Check status
pm2 status

# View logs
pm2 logs

# Restart bot
pm2 restart hypertracker-bot

# Update bot
./update.sh
```

## Troubleshooting

**Bot not starting?**
```bash
pm2 logs hypertracker-bot --lines 50
```

**Out of memory?**
```bash
./setup_swap.sh
```

**Update code from GitHub:**
```bash
./update.sh
```

## Files Created

- [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md) - Complete deployment guide
- [ecosystem.config.js](ecosystem.config.js) - PM2 configuration
- [deploy.sh](deploy.sh) - Automated deployment script
- [update.sh](update.sh) - Update script
- [setup_swap.sh](setup_swap.sh) - Swap file setup

## Support

Full documentation: [AWS_DEPLOYMENT_GUIDE.md](AWS_DEPLOYMENT_GUIDE.md)
