# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

HyperTracker Bot is a production-grade Telegram bot for real-time cryptocurrency trading monitoring on Hyperliquid. It provides sub-2-second latency notifications for wallet activities and cross-venue liquidation alerts using WebSocket connections.

**Tech Stack**: Python 3.11+, aiogram 3.14.0, aiosqlite, websockets, asyncio throughout

## Running the Bot

### Development
```bash
# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Run the bot (PREFERRED METHOD)
python run.py

# Alternative if run.py fails
PYTHONPATH=. python main.py
```

### Docker
```bash
docker-compose up -d        # Start in background
docker-compose logs -f      # View logs
docker-compose down         # Stop
```

### Environment Setup
- Copy `.env.example` to `.env`
- Add `BOT_TOKEN` from [@BotFather](https://t.me/botfather)
- All other settings have sensible defaults

## Architecture

### Application Flow
1. **Entry Point**: `main.py` contains `HyperTrackerBot` class that orchestrates everything
2. **Initialization** (`setup()`):
   - Creates database tables if needed
   - Loads all active wallets from DB
   - Initializes WebSocket clients for Hyperliquid and Chaos Labs
   - Subscribes to wallet addresses via WebSocket
   - Registers Telegram bot handlers
3. **Runtime**:
   - WebSocket clients run as background tasks with auto-reconnect
   - Incoming events trigger callbacks that check filters
   - Filtered events generate formatted notifications sent via Telegram
   - User interactions via Telegram update database and WebSocket subscriptions

### Core Components

**`core/hyperliquid_ws.py`** - WebSocket client for Hyperliquid
- Subscribes to individual wallet addresses using `{"method": "subscribe", "subscription": {"type": "userEvents", "user": "<address>"}}`
- Handles incoming events: `fills`, `funding`, `liquidation`, `nonUserCancel`
- Auto-reconnects with exponential backoff
- Maintains subscribed wallet set across reconnections

**`core/database.py`** - SQLite database layer
- Tables: `users`, `wallets`, `settings`
- Filters stored as JSON strings (`filters_json`, `liq_filters_json`)
- Key indexes: `idx_wallets_user_id`, `idx_wallets_address`, `idx_wallets_active`
- All operations are async using aiosqlite

**`core/models.py`** - Pydantic data models
- `Wallet` + `WalletFilters`: Per-wallet notification settings
- `UserSettings` + `LiquidationFilters`: Global liquidation monitoring
- `HyperliquidFill`, `HyperliquidDeposit`, `HyperliquidWithdrawal`: Event types
- `LiquidationEvent`: Cross-venue liquidation data
- Enums: `OrderType`, `Direction`, `NotificationType`

**`bot/notifier.py`** - Telegram notification delivery
- Handles Telegram rate limiting (50ms base delay between messages)
- Retries on `TelegramRetryAfter` errors
- Tracks blocked users to avoid repeated errors
- Uses plain text parse mode for emoji support

**`utils/filters.py`** - Event filtering logic
- `should_notify_fill()`: Checks if fill event matches wallet filters (asset, direction, min notional, notification type)
- `should_notify_liquidation()`: Checks if liquidation matches user filters (venue, pair, min notional)
- Asset filtering: `None` means all assets, otherwise list of symbols
- Direction: "A" = ask/sell, "B" = bid/buy in Hyperliquid API

**`bot/handlers/`** - Telegram command and callback handlers
- Uses aiogram Router pattern
- FSM (Finite State Machine) for multi-step flows (adding wallets, editing filters)
- Global `db` and `start_time` references set by main.py
- States: `AddWalletStates`, `EditWalletStates`, `EditLiquidationStates`

### WebSocket Subscription Model
- `main.py` maintains `wallet_map: Dict[str, list[Wallet]]` (address -> wallets)
- Multiple users can track the same address (each with different filters)
- When a user adds a wallet, `hyperliquid_ws.subscribe_wallet(address)` is called
- Events are broadcast to ALL wallets tracking that address, then filtered per-user
- **Important**: When modifying wallet subscription logic, remember to update both the in-memory `wallet_map` AND call WebSocket subscribe/unsubscribe methods

### Filter Persistence
- Filters are stored as JSON in database using `filters.model_dump()`
- When loading: `WalletFilters(**json.loads(row['filters_json']))`
- This allows schema evolution - add new filter fields without migration

## Common Tasks

### Adding a New Notification Type
1. Add enum value to `NotificationType` in `core/models.py`
2. Update `WalletFilters.notify_on` default in `core/models.py`
3. Add filter logic to `utils/filters.py`
4. Add formatting function to `utils/formatting.py`
5. Add notifier method to `bot/notifier.py`
6. Add callback handler in `bot/handlers/callbacks.py` for toggling the notification type

### Debugging WebSocket Issues
- Check `hypertracker.log` for connection and subscription logs
- WebSocket clients log at INFO level for connections, DEBUG for messages
- Subscription format must match: `{"method": "subscribe", "subscription": {"type": "userEvents", "user": "0x..."}}`
- The Hyperliquid WebSocket sends events directly as JSON objects with keys like `fills`, `funding`, `liquidation`

### Database Changes
- Database is created automatically on first run via `_create_tables()`
- To add a column: Add to CREATE TABLE, update model loading/saving code
- To add an index: Add CREATE INDEX in `_create_tables()`
- For schema migrations, consider writing a migration script that checks for column existence before adding

### Testing Filters
- Use `test_run.py` to verify imports
- For filter testing, create a test wallet with specific filters in DB manually
- Send test events through the WebSocket handlers to verify filtering logic
- Check notification output in Telegram

## Project-Specific Patterns

### Async/Await Usage
- ALL database calls use `await`
- ALL WebSocket operations use `await`
- Bot handlers are async by default (aiogram 3.x)
- Use `asyncio.create_task()` for background tasks (e.g., notifier callbacks)

### Error Handling
- WebSocket errors: Logged and trigger reconnect
- Database errors: Logged, return False/None
- Telegram errors: `TelegramRetryAfter` → retry, `TelegramForbiddenError` → mark user blocked
- Fill parsing errors: Logged with data for debugging, notification skipped

### Logging Strategy
- INFO: Connections, subscriptions, major state changes
- DEBUG: Individual events, message contents
- WARNING: Recoverable issues (rate limits, parsing failures)
- ERROR: Exceptions that affect functionality
- Logs go to stdout AND `hypertracker.log`

### Configuration
- `config.py` uses pydantic-settings to load from `.env`
- Settings singleton via `get_settings()`
- Default values for all settings except `BOT_TOKEN` (required)

## Known Limitations & TODOs

1. **Chaos Labs Liquidation User Filtering**: In `main.py:handle_chaos_liquidation()`, there's a TODO for user-level filtering. Currently structured but not fully implemented. Need to maintain in-memory set of users with liquidation monitoring enabled.

2. **Wallet Address Parsing**: `utils/filters.parse_wallet_addresses()` does basic splitting. May want to add validation for Ethereum-style addresses (0x prefix, length check).

3. **Spot vs Perp Detection**: Commented in `utils/filters.py` - Hyperliquid API may not clearly distinguish. The `OrderType` filter exists but isn't actively used.

4. **Rate Limiting**: Basic implementation with fixed 50ms delay. High-volume users may need adaptive rate limiting or batching.

5. **Future Features**: Placeholder modules in `core/` for:
   - `large_transfers_ws.py` - Whale wallet tracking
   - `oi_monitor.py` - Open interest monitoring
   - `funding_rate_tracker.py` - Funding rate alerts
   - `volume_anomaly_detector.py` - Volume spike detection

## File Naming & Module Structure

- Entry points in root: `run.py` (preferred), `main.py`, `launch.py`, `bot.py`
- Core business logic: `core/` (WebSockets, database, models)
- Telegram UI: `bot/` (handlers, keyboards, notifier)
- Utilities: `utils/` (filters, formatting)
- Config: `config.py` in root
- Data files: `data/` directory (created automatically)

## Important Notes

- **ALWAYS use `run.py` for development** - it sets PYTHONPATH correctly
- **Database path**: Default is `./data/hypertracker.db` (relative to project root)
- **WebSocket reconnect**: Uses exponential backoff from 1s to 60s max
- **Wallet subscription is idempotent**: Safe to call `subscribe_wallet()` multiple times
- **User IDs**: Store as `int` (Telegram user ID), not username (username can change)
- **Addresses**: Case-sensitive, stored exactly as provided by user
- **Timestamps**: Hyperliquid uses milliseconds, convert to datetime with `datetime.fromtimestamp(time/1000)`

## Dependencies

Install with: `pip install -r requirements.txt`

Core dependencies:
- `aiogram==3.14.0` - Telegram bot framework
- `aiohttp==3.10.10` - Async HTTP client
- `aiosqlite==0.20.0` - Async SQLite
- `pydantic==2.9.2` - Data validation
- `websockets==13.1` - WebSocket client
- `python-dotenv==1.0.1` - Environment variables
