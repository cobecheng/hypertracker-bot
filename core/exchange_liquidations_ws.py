"""
Individual exchange WebSocket clients for liquidation monitoring.
Replaces Chaos Labs with direct exchange connections for free, reliable data.
"""
import asyncio
import json
import logging
from typing import Callable, Optional
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed

from core.models import LiquidationEvent

logger = logging.getLogger(__name__)


class BinanceLiquidationWS:
    """
    Binance Futures liquidation WebSocket client.
    Uses the public force liquidation stream - completely free.
    """

    def __init__(
        self,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize Binance liquidation WebSocket client."""
        self.ws_url = "wss://fstream.binance.com/ws/!forceOrder@arr"
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False

        # Callback handler
        self.on_liquidation: Optional[Callable] = None

        self._current_delay = reconnect_delay

    async def start(self):
        """Start the WebSocket connection with auto-reconnect."""
        self.running = True

        while self.running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"Binance liquidation WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting to Binance in {self._current_delay} seconds...")
                    await asyncio.sleep(self._current_delay)
                    self._current_delay = min(self._current_delay * 2, self.max_reconnect_delay)

    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Binance liquidation WebSocket stopped")

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info(f"Connecting to Binance liquidation feed: {self.ws_url}")

        try:
            async with websockets.connect(
                self.ws_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout
            ) as ws:
                self.ws = ws
                logger.info("✅ Connected to Binance liquidation feed")
                self._current_delay = self.reconnect_delay

                # Listen for messages
                async for message in ws:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling Binance liquidation message: {e}")

        except ConnectionClosed:
            logger.warning("Binance liquidation WebSocket connection closed")
        except Exception as e:
            logger.error(f"Binance connection error: {e}")

    async def _handle_message(self, message: str):
        """Parse and route incoming liquidation messages."""
        try:
            data = json.loads(message)

            # Binance format: {"e": "forceOrder", "E": timestamp, "o": {...}}
            if data.get("e") == "forceOrder" and "o" in data:
                await self._handle_liquidation(data)

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode Binance message: {message}")
        except Exception as e:
            logger.error(f"Error handling Binance message: {e}")

    async def _handle_liquidation(self, data: dict):
        """Handle liquidation event from Binance."""
        try:
            order = data["o"]

            # Extract fields
            symbol = order.get("s", "")  # e.g., "BTCUSDT"
            side = order.get("S", "")  # "BUY" or "SELL"
            quantity = float(order.get("q", 0))
            price = float(order.get("p", 0))
            timestamp_ms = data.get("E", 0)

            # Calculate notional value
            notional_usd = quantity * price

            # Determine direction (opposite of side - if BUY order liquidated, was SHORT position)
            direction = "short" if side == "BUY" else "long"

            # Create liquidation event
            liquidation = LiquidationEvent(
                venue="Binance",
                pair=symbol,
                direction=direction,
                size=quantity,
                notional_usd=notional_usd,
                liquidation_price=price,
                address=None,  # Binance doesn't provide user address
                tx_hash=None,
                timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
            )

            logger.debug(f"Binance liquidation: {symbol} {direction} ${notional_usd:,.0f}")

            if self.on_liquidation:
                asyncio.create_task(self.on_liquidation(liquidation))

        except Exception as e:
            logger.error(f"Error parsing Binance liquidation: {e}")
            logger.debug(f"Data: {data}")


class BybitLiquidationWS:
    """
    Bybit liquidation WebSocket client.
    Monitors liquidations on Bybit Futures.
    """

    def __init__(
        self,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize Bybit liquidation WebSocket client."""
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False

        # Callback handler
        self.on_liquidation: Optional[Callable] = None

        self._current_delay = reconnect_delay

    async def start(self):
        """Start the WebSocket connection with auto-reconnect."""
        self.running = True

        while self.running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"Bybit liquidation WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting to Bybit in {self._current_delay} seconds...")
                    await asyncio.sleep(self._current_delay)
                    self._current_delay = min(self._current_delay * 2, self.max_reconnect_delay)

    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Bybit liquidation WebSocket stopped")

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info(f"Connecting to Bybit liquidation feed: {self.ws_url}")

        try:
            async with websockets.connect(
                self.ws_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout
            ) as ws:
                self.ws = ws
                logger.info("✅ Connected to Bybit liquidation feed")
                self._current_delay = self.reconnect_delay

                # Subscribe to liquidation topic
                await self._subscribe()

                # Listen for messages
                async for message in ws:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling Bybit liquidation message: {e}")

        except ConnectionClosed:
            logger.warning("Bybit liquidation WebSocket connection closed")
        except Exception as e:
            logger.error(f"Bybit connection error: {e}")

    async def _subscribe(self):
        """Subscribe to liquidation events."""
        # Subscribe to liquidation topic
        subscription = {
            "op": "subscribe",
            "args": ["liquidation.BTCUSDT", "liquidation.ETHUSDT"]
            # Add more pairs as needed
        }

        if self.ws:
            try:
                await self.ws.send(json.dumps(subscription))
                logger.info("Subscribed to Bybit liquidations")
            except Exception as e:
                logger.error(f"Error subscribing to Bybit: {e}")

    async def _handle_message(self, message: str):
        """Parse and route incoming liquidation messages."""
        try:
            data = json.loads(message)

            # Handle subscription response
            if data.get("op") == "subscribe":
                logger.info(f"Bybit subscription confirmed")
                return

            # Handle liquidation data
            if data.get("topic", "").startswith("liquidation"):
                await self._handle_liquidation(data)

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode Bybit message: {message}")
        except Exception as e:
            logger.error(f"Error handling Bybit message: {e}")

    async def _handle_liquidation(self, data: dict):
        """Handle liquidation event from Bybit."""
        try:
            liq_data = data.get("data", {})

            # Extract fields (adjust based on actual Bybit format)
            symbol = liq_data.get("symbol", "")
            side = liq_data.get("side", "")
            size = float(liq_data.get("size", 0))
            price = float(liq_data.get("price", 0))
            timestamp = liq_data.get("updatedTime", 0)

            # Calculate notional
            notional_usd = size * price

            # Create liquidation event
            liquidation = LiquidationEvent(
                venue="Bybit",
                pair=symbol,
                direction=side.lower(),
                size=size,
                notional_usd=notional_usd,
                liquidation_price=price,
                address=None,
                tx_hash=None,
                timestamp=datetime.fromtimestamp(timestamp / 1000) if timestamp else datetime.utcnow()
            )

            logger.debug(f"Bybit liquidation: {symbol} {side} ${notional_usd:,.0f}")

            if self.on_liquidation:
                asyncio.create_task(self.on_liquidation(liquidation))

        except Exception as e:
            logger.error(f"Error parsing Bybit liquidation: {e}")
            logger.debug(f"Data: {data}")


class MultiExchangeLiquidationWS:
    """
    Aggregator for multiple exchange liquidation feeds.
    Manages connections to Binance, Bybit, and other exchanges.
    """

    def __init__(
        self,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize multi-exchange liquidation aggregator."""
        self.binance = BinanceLiquidationWS(
            reconnect_delay, max_reconnect_delay, ping_interval, ping_timeout
        )
        self.bybit = BybitLiquidationWS(
            reconnect_delay, max_reconnect_delay, ping_interval, ping_timeout
        )

        # Callback handler
        self.on_liquidation: Optional[Callable] = None

    async def start(self):
        """Start all exchange WebSocket connections."""
        # Set callbacks
        self.binance.on_liquidation = self.on_liquidation
        self.bybit.on_liquidation = self.on_liquidation

        # Start connections
        logger.info("Starting multi-exchange liquidation monitoring...")
        await asyncio.gather(
            self.binance.start(),
            # self.bybit.start(),  # Uncomment when ready to add Bybit
        )

    async def stop(self):
        """Stop all exchange WebSocket connections."""
        logger.info("Stopping multi-exchange liquidation monitoring...")
        await asyncio.gather(
            self.binance.stop(),
            self.bybit.stop(),
        )
