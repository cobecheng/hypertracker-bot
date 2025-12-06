#!/usr/bin/env python3
"""
Test script for liquidation feeds from all venues.
Connects to CEX (Binance, Bybit, Gate.io) and DEX (Hyperliquid) and prints liquidation events in real-time.
"""
import asyncio
import logging
from datetime import datetime

from core.exchange_liquidations_ws import MultiExchangeLiquidationWS
from core.hyperliquid_ws import HyperliquidWebSocket
from core.models import LiquidationEvent
from config import get_settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Track liquidation counts by venue
liq_counts = {"Binance": 0, "Bybit": 0, "Gate.io": 0, "Hyperliquid": 0}


async def handle_liquidation(liquidation: LiquidationEvent):
    """Handle incoming liquidation events."""
    liq_counts[liquidation.venue] = liq_counts.get(liquidation.venue, 0) + 1

    print("\n" + "="*80)
    print(f"🔥 LIQUIDATION #{sum(liq_counts.values())} - {liquidation.venue}")
    print(f"Pair:      {liquidation.pair}")
    print(f"Direction: {liquidation.direction.upper()}")
    print(f"Size:      {liquidation.size:,.4f}")
    if liquidation.liquidation_price > 0:
        print(f"Price:     ${liquidation.liquidation_price:,.2f}")
    print(f"Notional:  ${liquidation.notional_usd:,.2f}")
    print(f"Time:      {liquidation.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    if liquidation.address:
        print(f"Address:   {liquidation.address[:10]}...{liquidation.address[-8:]}")
    print("="*80)


async def handle_hyperliquid_liquidation(data: dict):
    """Handle Hyperliquid liquidation events."""
    try:
        liquidated_user = data.get("liquidated_user", "")
        liquidated_ntl_pos = abs(float(data.get("liquidated_ntl_pos", 0)))
        raw_ntl_pos = float(data.get("liquidated_ntl_pos", 0))
        direction = "short" if raw_ntl_pos < 0 else "long"

        liquidation = LiquidationEvent(
            venue="Hyperliquid",
            pair="UNKNOWN",
            direction=direction,
            size=0.0,
            notional_usd=liquidated_ntl_pos,
            liquidation_price=0.0,
            address=liquidated_user,
            tx_hash=None,
            timestamp=datetime.now()
        )

        await handle_liquidation(liquidation)
    except Exception as e:
        logger.error(f"Error handling Hyperliquid liquidation: {e}")


async def print_stats():
    """Print statistics periodically."""
    await asyncio.sleep(60)  # Wait 1 minute before first print
    while True:
        print(f"\n📊 Liquidation Stats (last update: {datetime.now().strftime('%H:%M:%S')})")
        print(f"   Binance:     {liq_counts['Binance']:3d}")
        print(f"   Bybit:       {liq_counts['Bybit']:3d}")
        print(f"   Gate.io:     {liq_counts['Gate.io']:3d}")
        print(f"   Hyperliquid: {liq_counts['Hyperliquid']:3d}")
        print(f"   Total:       {sum(liq_counts.values()):3d}\n")
        await asyncio.sleep(60)  # Print every minute


async def main():
    """Main test function."""
    print("\n🚀 Starting Multi-Venue Liquidation Monitor")
    print(f"📊 CEX Venues: Binance, Bybit, Gate.io")
    print(f"🔷 DEX Venues: Hyperliquid")
    print(f"⏰ Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nWaiting for liquidation events...\n")
    print("💡 Tip: Gate.io may have fewer liquidations during low volatility")
    print("💡 Tip: Hyperliquid liquidations require active user subscriptions\n")

    settings = get_settings()

    # Initialize CEX liquidation client
    cex_client = MultiExchangeLiquidationWS()
    cex_client.on_liquidation = handle_liquidation

    # Initialize Hyperliquid client (for DEX liquidations)
    hl_client = HyperliquidWebSocket(
        ws_url=settings.HYPERLIQUID_WS_URL,
        rest_url=settings.HYPERLIQUID_REST_URL
    )
    hl_client.on_liquidation = handle_hyperliquid_liquidation

    try:
        # Start monitoring (runs indefinitely)
        await asyncio.gather(
            cex_client.start(),
            hl_client.start(),
            print_stats(),
        )
    except KeyboardInterrupt:
        logger.info("\n⚠️  Received interrupt signal, shutting down...")
        await cex_client.stop()
        await hl_client.stop()
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        await cex_client.stop()
        await hl_client.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Liquidation monitor stopped by user")
