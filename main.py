"""
HyperTracker Bot - Main Entry Point
Real-time Hyperliquid wallet tracking and cross-venue liquidation monitoring.
"""
import asyncio
import logging
import sys
import time
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import get_settings, ensure_data_directory
from core.database import Database
from core.hyperliquid_ws_pool import HyperliquidWebSocketPool
from core.exchange_liquidations_ws import MultiExchangeLiquidationWS
from core.models import (
    HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal,
    LiquidationEvent, Wallet
)
from bot.notifier import Notifier
from bot.handlers import commands, callbacks
from utils.filters import should_notify_fill, should_notify_liquidation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('hypertracker.log')
    ]
)
logger = logging.getLogger(__name__)


class HyperTrackerBot:
    """Main bot application orchestrating all components."""
    
    def __init__(self):
        """Initialize bot components."""
        self.settings = get_settings()
        
        # Core components
        self.bot = Bot(token=self.settings.bot_token)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.db: Database = None
        self.notifier: Notifier = None
        
        # WebSocket clients
        self.hyperliquid_ws: HyperliquidWebSocketPool = None
        self.exchange_liq_ws: MultiExchangeLiquidationWS = None
        
        # Wallet tracking
        self.wallet_map: Dict[str, list[Wallet]] = {}  # address -> list of wallets
        
        # Start time for uptime tracking
        self.start_time = time.time()
    
    async def setup(self):
        """Setup all components."""
        logger.info("Setting up HyperTracker Bot...")
        
        # Ensure data directory exists
        ensure_data_directory()
        
        # Initialize database
        self.db = Database(self.settings.database_path)
        await self.db.connect()
        
        # Initialize notifier
        self.notifier = Notifier(self.bot)
        
        # Setup handlers
        commands.db = self.db
        commands.start_time = self.start_time
        commands.reload_wallets_callback = self.load_active_wallets
        callbacks.db = self.db

        self.dp.include_router(commands.router)
        self.dp.include_router(callbacks.router)
        
        # Initialize WebSocket connection pool (one connection per user)
        self.hyperliquid_ws = HyperliquidWebSocketPool(
            ws_url=self.settings.hyperliquid_ws_url,
            rest_url=self.settings.hyperliquid_rest_url,
            reconnect_delay=self.settings.ws_reconnect_delay,
            max_reconnect_delay=self.settings.ws_max_reconnect_delay,
            ping_interval=self.settings.ws_ping_interval,
            ping_timeout=self.settings.ws_ping_timeout
        )
        
        # Initialize multi-exchange liquidation monitoring
        self.exchange_liq_ws = MultiExchangeLiquidationWS(
            reconnect_delay=self.settings.ws_reconnect_delay,
            max_reconnect_delay=self.settings.ws_max_reconnect_delay,
            ping_interval=self.settings.ws_ping_interval,
            ping_timeout=self.settings.ws_ping_timeout
        )

        # Set WebSocket callbacks
        self.hyperliquid_ws.on_fill = self.handle_fill
        self.hyperliquid_ws.on_deposit = self.handle_deposit
        self.hyperliquid_ws.on_withdrawal = self.handle_withdrawal
        self.hyperliquid_ws.on_liquidation = self.handle_hyperliquid_liquidation

        self.exchange_liq_ws.on_liquidation = self.handle_exchange_liquidation
        
        # Load and subscribe to active wallets
        await self.load_active_wallets()
        
        logger.info("Setup complete!")
    
    async def load_active_wallets(self):
        """Load all active wallets from database and subscribe to them."""
        wallets = await self.db.get_all_active_wallets()
        logger.info(f"Loading {len(wallets)} active wallets...")

        self.wallet_map.clear()

        for wallet in wallets:
            # Normalize address to lowercase for consistent matching
            normalized_address = wallet.address.lower()
            if normalized_address not in self.wallet_map:
                self.wallet_map[normalized_address] = []
            self.wallet_map[normalized_address].append(wallet)

        # Subscribe to unique addresses
        for address in self.wallet_map.keys():
            await self.hyperliquid_ws.subscribe_wallet(address)

        logger.info(f"Subscribed to {len(self.wallet_map)} unique wallet addresses")
        logger.info(f"Wallet addresses in map: {list(self.wallet_map.keys())}")
    
    async def handle_fill(self, fill: HyperliquidFill):
        """Handle fill event from Hyperliquid."""
        logger.info(f"Fill event for {fill.wallet}: {fill.coin} {fill.side} {fill.sz}")

        # Normalize address to lowercase for matching
        normalized_address = fill.wallet.lower() if fill.wallet else "unknown"

        # Get all wallets tracking this address
        wallets = self.wallet_map.get(normalized_address, [])
        logger.info(f"Found {len(wallets)} wallet(s) tracking address {normalized_address}")
        logger.info(f"Current wallet_map keys: {list(self.wallet_map.keys())}")

        if not wallets:
            logger.warning(f"No wallets found for address {normalized_address} - notification will not be sent")
            return

        for wallet in wallets:
            logger.info(f"Checking filters for wallet {wallet.id} (user {wallet.user_id}, alias: {wallet.alias})")

            # Get user's global filters
            user_settings = await self.db.get_user_settings(wallet.user_id)
            global_filters = user_settings.global_wallet_filters

            if global_filters:
                logger.info(f"Applying global filters: min_notional=${global_filters.min_notional_usd}, assets={global_filters.assets}")

            # Check if should notify based on filters (wallet + global)
            if should_notify_fill(fill, wallet, global_filters):
                logger.info(f"Filter passed! Sending notification to user {wallet.user_id}")
                await self.notifier.notify_fill(wallet.user_id, fill, wallet)
            else:
                logger.info(f"Filter check failed for wallet {wallet.id}")
    
    async def handle_deposit(self, deposit: HyperliquidDeposit):
        """Handle deposit event from Hyperliquid."""
        logger.debug(f"Deposit event for {deposit.wallet}: {deposit.usd}")
        
        wallets = self.wallet_map.get(deposit.wallet, [])
        
        for wallet in wallets:
            # Check if deposits are enabled in filters
            from core.models import NotificationType
            if (wallet.filters.notifications_enabled and 
                NotificationType.DEPOSIT in wallet.filters.notify_on):
                await self.notifier.notify_deposit(wallet.user_id, deposit, wallet)
    
    async def handle_withdrawal(self, withdrawal: HyperliquidWithdrawal):
        """Handle withdrawal event from Hyperliquid."""
        logger.debug(f"Withdrawal event for {withdrawal.wallet}: {withdrawal.usd}")
        
        wallets = self.wallet_map.get(withdrawal.wallet, [])
        
        for wallet in wallets:
            # Check if withdrawals are enabled in filters
            from core.models import NotificationType
            if (wallet.filters.notifications_enabled and 
                NotificationType.WITHDRAWAL in wallet.filters.notify_on):
                await self.notifier.notify_withdrawal(wallet.user_id, withdrawal, wallet)
    
    async def handle_hyperliquid_liquidation(self, data: dict):
        """Handle liquidation from Hyperliquid WebSocket."""
        logger.info(f"Hyperliquid liquidation: {data}")
        # This can be processed similar to Chaos Labs liquidations
        # For now, we'll let Chaos Labs handle cross-venue liquidations
    
    async def handle_exchange_liquidation(self, liquidation: LiquidationEvent):
        """Handle liquidation event from exchange feeds (Binance, Bybit, etc.)."""
        logger.info(f"Liquidation: {liquidation.venue} {liquidation.pair} ${liquidation.notional_usd:,.0f}")

        # Get all users from database
        # Note: For optimization with many users, maintain an in-memory cache
        # of users with liquidation monitoring enabled
        all_users = await self.db.get_all_users()

        for user in all_users:
            # Get user settings
            user_settings = await self.db.get_user_settings(user.telegram_id)

            # Check if user has liquidation monitoring enabled
            if not user_settings.liquidation_filters.enabled:
                continue

            # Check if liquidation passes user's filters
            if should_notify_liquidation(liquidation, user_settings.liquidation_filters):
                logger.info(f"Sending liquidation notification to user {user.telegram_id}")
                await self.notifier.notify_liquidation(user.telegram_id, liquidation)
    
    async def start(self):
        """Start the bot and all background tasks."""
        logger.info("Starting HyperTracker Bot...")

        # Start exchange liquidation monitoring in background
        asyncio.create_task(self.exchange_liq_ws.start())

        # Start polling
        try:
            await self.dp.start_polling(self.bot, allowed_updates=self.dp.resolve_used_update_types())
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down HyperTracker Bot...")

        # Stop all WebSocket connections
        await self.hyperliquid_ws.stop_all()
        await self.exchange_liq_ws.stop()

        # Close database
        await self.db.close()

        # Close bot session
        await self.bot.session.close()

        logger.info("Shutdown complete")


async def main():
    """Main entry point."""
    bot = HyperTrackerBot()
    
    try:
        await bot.setup()
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
