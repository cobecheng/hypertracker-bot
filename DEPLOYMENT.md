# HyperTracker Bot - Deployment Guide

## Prerequisites

Before deploying, ensure you have:

1. **Telegram Bot Token**
   - Create a bot via [@BotFather](https://t.me/botfather)
   - Use `/newbot` command and follow instructions
   - Save the bot token securely

2. **Server Requirements**
   - Linux server (Ubuntu 20.04+ recommended)
   - Docker & Docker Compose installed
   - At least 512MB RAM
   - Stable internet connection

## Deployment Steps

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd hypertracker_bot
```

### 2. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file with your configuration
nano .env
```

**Required configuration in `.env`:**
```env
BOT_TOKEN=your_telegram_bot_token_here
```

**Optional configurations:**
```env
# Database path (default: ./data/hypertracker.db)
DATABASE_PATH=./data/hypertracker.db

# WebSocket URLs (defaults are usually fine)
HYPERLIQUID_WS_URL=wss://api.hyperliquid.xyz/ws
HYPERLIQUID_REST_URL=https://api.hyperliquid.xyz/info
CHAOS_LABS_WS_URL=wss://data.chaoslabs.xyz/ws/liquidations

# Performance tuning
WS_RECONNECT_DELAY=1
WS_MAX_RECONNECT_DELAY=60
WS_PING_INTERVAL=20
WS_PING_TIMEOUT=10

# Logging
LOG_LEVEL=INFO
```

### 3. Deploy with Docker Compose

```bash
# Build and start the bot
docker-compose up -d

# View logs
docker-compose logs -f

# Check status
docker-compose ps
```

### 4. Verify Deployment

1. Open Telegram and find your bot
2. Send `/start` command
3. You should receive a welcome message with the main menu

### 5. Monitor the Bot

```bash
# View live logs
docker-compose logs -f hypertracker

# View last 100 lines
docker-compose logs --tail=100 hypertracker

# Check container status
docker-compose ps

# Restart the bot
docker-compose restart

# Stop the bot
docker-compose stop

# Stop and remove containers
docker-compose down
```

## Alternative: Local Development Deployment

If you prefer to run without Docker:

### 1. Install Python Dependencies

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your bot token
```

### 3. Run the Bot

```bash
python main.py
```

### 4. Keep Bot Running (Production)

Use a process manager like `systemd` or `supervisor`:

**Example systemd service (`/etc/systemd/system/hypertracker.service`):**

```ini
[Unit]
Description=HyperTracker Telegram Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hypertracker_bot
Environment="PATH=/home/ubuntu/hypertracker_bot/venv/bin"
ExecStart=/home/ubuntu/hypertracker_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable hypertracker
sudo systemctl start hypertracker
sudo systemctl status hypertracker
```

## Production Deployment Checklist

- [ ] Bot token configured in `.env`
- [ ] `.env` file has proper permissions (not world-readable)
- [ ] Data directory has proper permissions
- [ ] Firewall allows outbound HTTPS and WebSocket connections
- [ ] Logs are being written and rotated
- [ ] Bot responds to `/start` command
- [ ] WebSocket connections are established (check logs)
- [ ] Database is being created in data directory
- [ ] Monitoring/alerting configured (optional)

## Updating the Bot

### With Docker:

```bash
# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Verify
docker-compose logs -f
```

### Without Docker:

```bash
# Pull latest changes
git pull

# Activate virtual environment
source venv/bin/activate

# Update dependencies
pip install -r requirements.txt

# Restart the bot
# If using systemd:
sudo systemctl restart hypertracker

# If running manually:
# Stop with Ctrl+C and restart with:
python main.py
```

## Backup and Recovery

### Backup Database

```bash
# With Docker
docker-compose exec hypertracker cp /app/data/hypertracker.db /app/data/backup.db

# Copy to host
docker cp hypertracker_bot:/app/data/hypertracker.db ./backup/

# Without Docker
cp data/hypertracker.db backup/hypertracker_$(date +%Y%m%d).db
```

### Restore Database

```bash
# With Docker
docker cp backup/hypertracker.db hypertracker_bot:/app/data/
docker-compose restart

# Without Docker
cp backup/hypertracker.db data/
# Restart the bot
```

## Troubleshooting

### Bot not starting

1. Check logs: `docker-compose logs hypertracker`
2. Verify bot token in `.env`
3. Check Python version: `python3.11 --version`
4. Verify dependencies: `pip list`

### WebSocket connection failures

1. Check internet connectivity
2. Verify WebSocket URLs in `.env`
3. Check firewall rules
4. Look for reconnection attempts in logs

### Database errors

1. Check data directory permissions
2. Verify DATABASE_PATH in `.env`
3. Check disk space: `df -h`
4. Try removing database (will lose data): `rm data/hypertracker.db`

### High memory usage

1. Check number of tracked wallets
2. Monitor WebSocket connections
3. Consider increasing server resources
4. Check for memory leaks in logs

### Rate limiting issues

1. Reduce notification frequency
2. Check Telegram rate limits in logs
3. Implement additional rate limiting if needed

## Security Best Practices

1. **Never commit `.env` file** - It contains sensitive tokens
2. **Use strong server passwords** - Secure your deployment server
3. **Keep dependencies updated** - Run `pip list --outdated` regularly
4. **Monitor logs** - Watch for suspicious activity
5. **Backup regularly** - Automate database backups
6. **Use HTTPS** - For any web interfaces (if added)
7. **Limit access** - Use firewall rules to restrict access

## Performance Optimization

1. **Database indexing** - Already implemented in schema
2. **WebSocket reconnection** - Auto-reconnect with exponential backoff
3. **Rate limiting** - Built-in Telegram rate limit handling
4. **Async operations** - All I/O is non-blocking
5. **Connection pooling** - Consider for high user counts

## Monitoring

### Key Metrics to Monitor

- Bot uptime
- WebSocket connection status
- Number of active users
- Number of tracked wallets
- Database size
- Memory usage
- CPU usage
- Error rate in logs

### Recommended Tools

- **Logs**: Docker logs, systemd journal
- **Metrics**: Prometheus + Grafana (optional)
- **Alerts**: Email, Telegram, Slack notifications
- **Uptime**: UptimeRobot, Pingdom

## Support

For issues or questions:
1. Check the logs first
2. Review this deployment guide
3. Check the main README.md
4. Open an issue on GitHub

---

**Happy Tracking! 🚀**
