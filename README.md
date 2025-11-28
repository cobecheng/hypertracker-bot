# HyperTracker Bot 🚀

A production-grade Telegram bot for real-time Hyperliquid wallet tracking and cross-venue liquidation monitoring with sub-2-second latency.

## Features

### 🎯 Hyperliquid Wallet Tracker
- **Real-time monitoring** of wallet activities via WebSocket
- **Per-wallet customizable notifications** for:
  - Opens, Closes, Fills
  - Liquidations
  - Deposits & Withdrawals
- **Advanced filtering**:
  - Filter by asset (BTC, ETH, SOL, etc.)
  - Filter by order type (Spot/Perp)
  - Filter by direction (Long/Short/Both)
  - Minimum notional size in USD
- **Beautiful notifications** with emojis and formatted data
- **Wallet aliases** for easy identification

### 🚨 Large Liquidation Monitor
- **Cross-venue monitoring** (Hyperliquid, Lighter, Binance, Bybit, OKX, gTrade)
- **Customizable filters**:
  - Select specific venues
  - Filter by trading pairs
  - Minimum notional USD threshold
- **Real-time alerts** for large liquidations
- **Powered by Chaos Labs** WebSocket feed for fastest multi-CEX data

### ⚡ Performance
- **Sub-2-second latency** from event to Telegram notification
- **Auto-reconnecting WebSocket** clients with exponential backoff
- **Graceful error handling** and rate limiting
- **Production-ready** with Docker support

## Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (optional but recommended)
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))

### Installation

#### Option 1: Docker (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd hypertracker_bot
```

2. Create `.env` file:
```bash
cp .env.example .env
```

3. Edit `.env` and add your bot token:
```env
BOT_TOKEN=your_telegram_bot_token_here
```

4. Start the bot:
```bash
docker-compose up -d
```

5. View logs:
```bash
docker-compose logs -f
```

#### Option 2: Local Development

1. Clone and setup:
```bash
git clone <repository-url>
cd hypertracker_bot
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your bot token
```

3. Run the bot:

**Using the startup script (Recommended):**
```bash
# On macOS/Linux:
./start.sh

# On Windows:
start.bat
```

**Or using Python directly:**
```bash
python run.py
```

**Alternative (if run.py doesn't work):**
```bash
# macOS/Linux:
PYTHONPATH=. python main.py

# Windows (Command Prompt):
set PYTHONPATH=.
python main.py

# Windows (PowerShell):
$env:PYTHONPATH="."
python main.py
```

## Usage

### Commands
- `/start` - Welcome message and main menu
- `/stats` - Bot statistics (users, wallets, uptime)
- `/cancel` - Cancel current operation

### Main Features

#### Add Wallet
1. Click "➕ Add Wallet" in the main menu
2. Send one or more Hyperliquid wallet addresses
3. Optionally provide an alias for easy identification
4. Configure notification filters

#### My Wallets
1. Click "📋 My Wallets" to view all tracked wallets
2. Select a wallet to view details
3. Edit filters, toggle notifications, or remove wallet

#### Liquidation Monitor
1. Click "🚨 Liquidation Monitor"
2. Toggle alerts on/off
3. Configure venues, pairs, and minimum notional
4. Receive real-time liquidation alerts

## Project Structure

```
hypertracker_bot/
├── run.py                       # Main entry point (USE THIS)
├── main.py                      # Application logic
├── config.py                    # Configuration management
├── requirements.txt             # Python dependencies
├── start.sh                     # Unix startup script
├── start.bat                    # Windows startup script
├── Dockerfile                   # Docker container definition
├── docker-compose.yml           # Docker Compose configuration
├── .env.example                 # Environment variables template
├── QUICKSTART.md                # Quick start guide
├── bot/
│   ├── handlers/
│   │   ├── commands.py          # Command handlers
│   │   └── callbacks.py         # Callback query handlers
│   ├── keyboards.py             # Inline keyboards
│   └── notifier.py              # Notification system
├── core/
│   ├── database.py              # SQLite database layer
│   ├── models.py                # Pydantic models
│   ├── hyperliquid_ws.py        # Hyperliquid WebSocket client
│   ├── chaos_liquidations_ws.py # Chaos Labs WebSocket client
│   └── [future modules...]      # Extensibility placeholders
└── utils/
    ├── filters.py               # Event filtering logic
    └── formatting.py            # Message formatting utilities
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `BOT_TOKEN` | Telegram bot token | **Required** |
| `DATABASE_PATH` | SQLite database path | `./data/hypertracker.db` |
| `HYPERLIQUID_WS_URL` | Hyperliquid WebSocket URL | `wss://api.hyperliquid.xyz/ws` |
| `HYPERLIQUID_REST_URL` | Hyperliquid REST API URL | `https://api.hyperliquid.xyz/info` |
| `CHAOS_LABS_WS_URL` | Chaos Labs WebSocket URL | `wss://data.chaoslabs.xyz/ws/liquidations` |
| `WS_RECONNECT_DELAY` | Initial reconnect delay (seconds) | `1` |
| `WS_MAX_RECONNECT_DELAY` | Max reconnect delay (seconds) | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Troubleshooting

### ModuleNotFoundError: No module named 'core'

**Solution**: Use `python run.py` instead of `python main.py`, or set PYTHONPATH:
```bash
# macOS/Linux
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python main.py

# Windows
set PYTHONPATH=%PYTHONPATH%;%CD%
python main.py
```

### Bot not responding
1. Check if the bot is running: `docker-compose ps` or check terminal
2. View logs: `docker-compose logs -f` or check `hypertracker.log`
3. Verify bot token in `.env`
4. Ensure bot has proper permissions in Telegram

### WebSocket connection issues
1. Check internet connectivity
2. Verify WebSocket URLs in configuration
3. Check logs for reconnection attempts
4. Ensure firewall allows WebSocket connections

### Database errors
1. Check database file permissions
2. Ensure data directory exists
3. Try removing database and restarting (will lose data)

## Development

### Running Tests
```bash
python test_run.py  # Test imports
python test_imports.py  # Full import test
```

### Code Style
```bash
# Format code
black .

# Lint code
pylint bot/ core/ utils/
```

## Performance Optimization

- **WebSocket connections**: Auto-reconnecting with exponential backoff
- **Rate limiting**: Built-in Telegram rate limit handling
- **Database**: Indexed queries for fast lookups
- **Async/await**: Non-blocking I/O throughout

## Security

- **Environment variables**: Sensitive data in `.env` (not committed)
- **Docker**: Isolated container environment
- **Input validation**: All user inputs validated
- **Error handling**: Graceful error handling without exposing internals

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues, questions, or feature requests:
- Check QUICKSTART.md for common setup issues
- Review DEPLOYMENT.md for production deployment
- Check logs in `hypertracker.log`
- Open an issue on GitHub

## Acknowledgments

- [Hyperliquid](https://hyperliquid.xyz) for the trading platform and API
- [Chaos Labs](https://chaoslabs.xyz) for cross-venue liquidation data
- [aiogram](https://aiogram.dev) for the excellent Telegram bot framework

---

Built with ❤️ for the crypto trading community
