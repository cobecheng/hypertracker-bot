"""
HyperTracker Bot - Main Entry Point
Real-time Hyperliquid wallet tracking and cross-venue liquidation monitoring.
"""
import asyncio
import sys
import time
from datetime import datetime
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import get_settings, ensure_data_directory
from core.database import Database
from core.hyperliquid_ws_pool import HyperliquidWebSocketPool
from core.exchange_liquidations_ws import MultiExchangeLiquidationWS
from core.models import (
    HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal,
    HyperliquidTwapOrder, LiquidationEvent, Wallet
)
from bot.notifier import Notifier
from bot.handlers import commands, callbacks, evm_commands
from utils.filters import should_notify_fill, should_notify_liquidation
from utils.logging_config import setup_logging

# Configure advanced logging system
loggers = setup_logging(log_level="INFO")
logger = loggers['system']
liquidations_logger = loggers['liquidations']
fills_logger = loggers['fills']


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

        # Liquidation statistics tracking (last hour)
        self.liq_stats = {
            'Binance': {'total': 0, 'sent': 0, 'last_reset': datetime.now()},
            'Bybit': {'total': 0, 'sent': 0, 'last_reset': datetime.now()},
            'Gate.io': {'total': 0, 'sent': 0, 'last_reset': datetime.now()},
        }
    
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
        callbacks.liq_stats = self.liq_stats  # Share liquidation stats with handlers

        # Setup EVM tracking handlers
        evm_commands.db = self.db

        self.dp.include_router(commands.router)
        self.dp.include_router(callbacks.router)
        self.dp.include_router(evm_commands.router)

        # Initialize spot asset mapper and fetch metadata
        # This will be used by WebSocket clients to resolve @107 -> HYPE
        logger.info("Initializing spot asset mapper...")
        from utils.spot_assets import get_spot_mapper
        spot_mapper = get_spot_mapper(self.settings.hyperliquid_rest_url)
        await spot_mapper.initialize()

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
        self.hyperliquid_ws.on_twap = self.handle_twap

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

        # Check if we're exceeding Hyperliquid's API limit
        unique_addresses = list(self.wallet_map.keys())
        max_allowed = self.hyperliquid_ws.MAX_USERS_PER_IP

        if len(unique_addresses) > max_allowed:
            logger.warning(
                f"⚠️  WARNING: {len(unique_addresses)} unique wallet addresses configured, "
                f"but Hyperliquid API limits to {max_allowed} per IP address. "
                f"Only the first {max_allowed} wallets will be monitored."
            )
            # Only subscribe to the first MAX_USERS_PER_IP addresses
            unique_addresses = unique_addresses[:max_allowed]

        # Subscribe to unique addresses (up to API limit)
        subscribed_count = 0
        failed_addresses = []

        for address in unique_addresses:
            try:
                await self.hyperliquid_ws.subscribe_wallet(address)
                subscribed_count += 1
            except ValueError as e:
                logger.error(f"Failed to subscribe to {address}: {e}")
                failed_addresses.append(address)

        logger.info(f"✓ Successfully subscribed to {subscribed_count}/{len(self.wallet_map)} unique wallet addresses")

        if failed_addresses:
            logger.warning(f"✗ Failed to subscribe to {len(failed_addresses)} addresses: {failed_addresses}")

        logger.info(f"Wallet addresses being monitored: {unique_addresses[:subscribed_count]}")
    
    async def handle_fill(self, fill: HyperliquidFill):
        """Handle fill event from Hyperliquid."""
        # Log to dedicated fills log file
        fills_logger.info(f"{fill.wallet[:10]}... {fill.coin} {fill.side} {fill.sz} @ ${fill.px}")

        # Normalize address to lowercase for matching
        normalized_address = fill.wallet.lower() if fill.wallet else "unknown"

        # Get all wallets (tracking configurations) for this address
        wallets = self.wallet_map.get(normalized_address, [])
        logger.info(f"Found {len(wallets)} user(s) tracking address {normalized_address}")
        logger.info(f"Current wallet_map keys: {list(self.wallet_map.keys())}")

        if not wallets:
            logger.warning(f"No users found tracking address {normalized_address} - notification will not be sent")
            return

        for wallet in wallets:
            logger.info(f"Checking filters for user {wallet.user_id} (wallet_id: {wallet.id}, alias: {wallet.alias})")

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

    async def handle_twap(self, twap: HyperliquidTwapOrder):
        """Handle TWAP order event from Hyperliquid."""
        logger.info(f"TWAP order event for {twap.wallet}: {twap.coin} {twap.side} {twap.sz} (status: {twap.status})")

        # Normalize address to lowercase for matching
        normalized_address = twap.wallet.lower() if twap.wallet else "unknown"

        # Get all wallets tracking this address
        wallets = self.wallet_map.get(normalized_address, [])
        logger.info(f"Found {len(wallets)} wallet(s) tracking address {normalized_address}")

        if not wallets:
            logger.warning(f"No wallets found for address {normalized_address} - notification will not be sent")
            return

        for wallet in wallets:
            logger.info(f"Checking filters for wallet {wallet.id} (user {wallet.user_id}, alias: {wallet.alias})")

            # Check if TWAP notifications are enabled in filters
            from core.models import NotificationType

            # Check for activated TWAP orders
            if twap.status == "activated":
                if (wallet.filters.notifications_enabled and
                    NotificationType.TWAP in wallet.filters.notify_on):
                    logger.info(f"TWAP activation notifications enabled! Sending notification to user {wallet.user_id}")
                    await self.notifier.notify_twap(wallet.user_id, twap, wallet)
                else:
                    logger.info(f"TWAP activation notifications not enabled for wallet {wallet.id}")

            # Check for terminated/cancelled TWAP orders
            elif twap.status == "terminated":
                if (wallet.filters.notifications_enabled and
                    NotificationType.TWAP_CANCEL in wallet.filters.notify_on):
                    logger.info(f"TWAP cancellation notifications enabled! Sending notification to user {wallet.user_id}")
                    await self.notifier.notify_twap(wallet.user_id, twap, wallet)
                else:
                    logger.info(f"TWAP cancellation notifications not enabled for wallet {wallet.id}")

    async def handle_hyperliquid_liquidation(self, data: dict):
        """
        Handle liquidation from Hyperliquid WebSocket.
        Converts Hyperliquid liquidation format to LiquidationEvent and routes to users.

        Hyperliquid format:
        {
            "lid": int,
            "liquidator": str (address),
            "liquidated_user": str (address),
            "liquidated_ntl_pos": str (notional position value),
            "liquidated_account_value": str (account value at liquidation)
        }
        """
        try:
            logger.info(f"Hyperliquid liquidation event: {data}")

            # Extract fields from Hyperliquid format
            liquidated_user = data.get("liquidated_user", "")
            liquidated_ntl_pos = abs(float(data.get("liquidated_ntl_pos", 0)))
            account_value = float(data.get("liquidated_account_value", 0))

            # Determine direction from notional position (negative = short, positive = long)
            raw_ntl_pos = float(data.get("liquidated_ntl_pos", 0))
            direction = "short" if raw_ntl_pos < 0 else "long"

            # Create LiquidationEvent
            liquidation = LiquidationEvent(
                venue="Hyperliquid",
                pair="UNKNOWN",  # Hyperliquid doesn't specify pair in liquidation event
                direction=direction,
                size=0.0,  # Not available in liquidation event
                notional_usd=liquidated_ntl_pos,
                liquidation_price=0.0,  # Not available in liquidation event
                address=liquidated_user,
                tx_hash=None,
                timestamp=datetime.now()
            )

            logger.info(f"Hyperliquid liquidation: {direction} ${liquidated_ntl_pos:,.0f} (user: {liquidated_user})")

            # Route to exchange liquidation handler (same as CEX liquidations)
            await self.handle_exchange_liquidation(liquidation)

        except Exception as e:
            logger.error(f"Error handling Hyperliquid liquidation: {e}")
            logger.debug(f"Data: {data}")
    
    async def handle_exchange_liquidation(self, liquidation: LiquidationEvent):
        """Handle liquidation event from exchange feeds (Binance, Bybit, etc.)."""
        # Log to dedicated liquidations log file
        liquidations_logger.info(f"{liquidation.venue} {liquidation.pair} {liquidation.direction} ${liquidation.notional_usd:,.0f}")

        # Update statistics - track total liquidations received
        venue = liquidation.venue
        if venue in self.liq_stats:
            # Reset stats if more than 1 hour has passed
            now = datetime.now()
            if (now - self.liq_stats[venue]['last_reset']).total_seconds() > 3600:
                self.liq_stats[venue]['total'] = 0
                self.liq_stats[venue]['sent'] = 0
                self.liq_stats[venue]['last_reset'] = now

            # Increment total count (includes filtered out)
            self.liq_stats[venue]['total'] += 1

        # Get all users from database
        # Note: For optimization with many users, maintain an in-memory cache
        # of users with liquidation monitoring enabled
        all_users = await self.db.get_all_users()

        notification_sent = False
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
                notification_sent = True

        # Update sent count if at least one notification was sent
        if notification_sent and venue in self.liq_stats:
            self.liq_stats[venue]['sent'] += 1
    
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
