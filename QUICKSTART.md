# HyperTracker Bot - Quick Start Guide

## Installation & Setup

### Step 1: Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Bot Token

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your Telegram bot token
# Get your token from @BotFather on Telegram
nano .env  # or use any text editor
```

Your `.env` file should look like:
```env
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
```

### Step 3: Run the Bot

**Option 1: Using the startup script (Recommended)**

On macOS/Linux:
```bash
./start.sh
```

On Windows:
```bash
start.bat
```

**Option 2: Using Python directly**

```bash
python run.py
```

**Option 3: Using the original main.py (with PYTHONPATH)**

On macOS/Linux:
```bash
PYTHONPATH=. python main.py
```

On Windows (Command Prompt):
```cmd
set PYTHONPATH=.
python main.py
```

On Windows (PowerShell):
```powershell
$env:PYTHONPATH="."
python main.py
```

## Verifying the Bot Works

1. The bot should start and show logs like:
   ```
   INFO - Setting up HyperTracker Bot...
   INFO - Database connected: ./data/hypertracker.db
   INFO - Connected to Hyperliquid WebSocket
   INFO - Subscribed to liquidations
   INFO - Setup complete!
   ```

2. Open Telegram and find your bot
3. Send `/start` command
4. You should receive a welcome message with buttons

## Troubleshooting

### "ModuleNotFoundError: No module named 'core'"

**Solution**: Use `python run.py` instead of `python main.py`, or set PYTHONPATH:
```bash
# macOS/Linux
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python main.py

# Windows
set PYTHONPATH=%PYTHONPATH%;%CD%
python main.py
```

### "No module named 'aiogram'" or other dependencies

**Solution**: Make sure you've installed dependencies and activated the virtual environment:
```bash
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### "BOT_TOKEN not found" or bot doesn't respond

**Solution**: 
1. Make sure `.env` file exists (copy from `.env.example`)
2. Add your bot token from @BotFather
3. Restart the bot

### WebSocket connection errors

**Solution**:
1. Check your internet connection
2. Verify the WebSocket URLs in `.env` are correct
3. Check if a firewall is blocking WebSocket connections

## Docker Alternative

If you prefer Docker (no Python installation needed):

```bash
# Create .env file with your bot token
cp .env.example .env
nano .env

# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the bot
docker-compose down
```

## Next Steps

Once the bot is running:

1. **Add a wallet**: Click "➕ Add Wallet" and send a Hyperliquid address
2. **Configure filters**: Select a wallet and click "✏️ Edit Filters"
3. **Enable liquidation alerts**: Click "🚨 Liquidation Monitor"
4. **Check stats**: Use `/stats` command

## Getting Help

- Check the full README.md for detailed documentation
- Review DEPLOYMENT.md for production deployment
- Check logs in `hypertracker.log` file
- Ensure all prerequisites are met (Python 3.11+, dependencies installed)

---

**Happy Tracking! 🚀**
