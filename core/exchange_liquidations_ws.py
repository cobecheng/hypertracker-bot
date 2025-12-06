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
    Uses the new 'all-liquidation' API (Feb 2025) for complete liquidation coverage.
    Updates every 500ms with all liquidations (vs previous 1 msg/sec/symbol limit).
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

                # Subscribe to all-liquidation topic (new Feb 2025 API)
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
        """Subscribe to all-liquidation events using the new comprehensive API.

        Note: Not all pairs support liquidation streams. We subscribe individually
        to handle failures gracefully and only track supported pairs.
        """
        # Bybit all-liquidation format: allLiquidation.{symbol}
        # Attempting major trading pairs - Bybit only supports liquidation streams on select pairs
        candidate_pairs = [
            # Top tier (highest volume) - most likely to have liquidation support
            "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
            # Layer 1s
            "ADAUSDT", "AVAXUSDT", "DOTUSDT", "ATOMUSDT", "NEARUSDT",
            "APTUSDT", "SUIUSDT", "TONUSDT",
            # DeFi
            "LINKUSDT", "UNIUSDT", "AAVEUSDT",
            # Layer 2s & Scaling
            "ARBUSDT", "OPUSDT", "MATICUSDT",
            # Memecoins (high volatility but may not be supported)
            "DOGEUSDT",
            # Other popular
            "LTCUSDT", "ETCUSDT", "FTMUSDT",
        ]

        if not self.ws:
            return

        # Subscribe to all pairs at once - we'll track which ones succeed via responses
        subscription_topics = [f"allLiquidation.{pair}" for pair in candidate_pairs]
        subscription = {
            "op": "subscribe",
            "args": subscription_topics
        }

        try:
            await self.ws.send(json.dumps(subscription))
            logger.info(f"Attempting Bybit liquidation subscription for {len(candidate_pairs)} pairs...")
            # Success/failure will be logged in _handle_message when responses arrive
        except Exception as e:
            logger.error(f"Error subscribing to Bybit: {e}")

    async def _handle_message(self, message: str):
        """Parse and route incoming liquidation messages."""
        try:
            data = json.loads(message)

            # Handle subscription response
            if data.get("op") == "subscribe":
                success = data.get("success", False)
                if success:
                    # Only log first successful subscription to avoid spam
                    if not hasattr(self, '_subscription_confirmed'):
                        self._subscription_confirmed = True
                        logger.info(f"✅ Bybit liquidation subscriptions active")
                else:
                    # Silently ignore failed subscriptions - many pairs don't support liquidation streams
                    # This is expected behavior, not an error
                    ret_msg = data.get("ret_msg", "")
                    if "handler not found" in ret_msg:
                        # Extract pair name from error message if available
                        logger.debug(f"Bybit liquidation stream not available for some pairs (expected)")
                    else:
                        # Log unexpected subscription errors
                        logger.warning(f"Bybit subscription issue: {data}")
                return

            # Handle pong responses
            if data.get("op") == "pong":
                return

            # Handle liquidation data (topic format: allLiquidation.BTCUSDT)
            topic = data.get("topic", "")
            if topic.startswith("allLiquidation."):
                await self._handle_liquidation(data)

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode Bybit message: {message}")
        except Exception as e:
            logger.error(f"Error handling Bybit message: {e}")

    async def _handle_liquidation(self, data: dict):
        """Handle liquidation event from Bybit all-liquidation stream."""
        try:
            # Bybit all-liquidation format: {"topic": "...", "type": "snapshot", "ts": ..., "data": [...]}
            liquidations = data.get("data", [])

            for liq_data in liquidations:
                # Extract fields from Bybit format
                symbol = liq_data.get("s", "")  # Symbol (e.g., "BTCUSDT")
                side = liq_data.get("S", "")    # Side: "Buy" or "Sell"
                size = float(liq_data.get("v", 0))  # Volume/size
                price = float(liq_data.get("p", 0))  # Price
                timestamp_ms = int(liq_data.get("T", 0))  # Timestamp in milliseconds

                # Calculate notional value
                notional_usd = size * price

                # Determine direction (opposite of liquidation order side)
                # If liquidation order is Buy, the position was Short
                direction = "short" if side == "Buy" else "long"

                # Create liquidation event
                liquidation = LiquidationEvent(
                    venue="Bybit",
                    pair=symbol,
                    direction=direction,
                    size=size,
                    notional_usd=notional_usd,
                    liquidation_price=price,
                    address=None,  # Bybit doesn't provide user address
                    tx_hash=None,
                    timestamp=datetime.fromtimestamp(timestamp_ms / 1000)
                )

                logger.debug(f"Bybit liquidation: {symbol} {direction} ${notional_usd:,.0f}")

                if self.on_liquidation:
                    asyncio.create_task(self.on_liquidation(liquidation))

        except Exception as e:
            logger.error(f"Error parsing Bybit liquidation: {e}")
            logger.debug(f"Data: {data}")


class GateIOLiquidationWS:
    """
    Gate.io liquidation WebSocket client.
    Uses the new 'futures.public_liquidates' channel (added Feb 2025).
    Monitors liquidations on Gate.io futures markets.
    """

    def __init__(
        self,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize Gate.io liquidation WebSocket client."""
        # Gate.io has multiple settlement currencies: btc, usdt, usd
        # We'll use USDT perpetuals as the primary feed
        # Note: Domain is gateio.ws (not gate.io)
        self.ws_url = "wss://fx-ws.gateio.ws/v4/ws/usdt"
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
                logger.error(f"Gate.io liquidation WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting to Gate.io in {self._current_delay} seconds...")
                    await asyncio.sleep(self._current_delay)
                    self._current_delay = min(self._current_delay * 2, self.max_reconnect_delay)

    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Gate.io liquidation WebSocket stopped")

    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info(f"Connecting to Gate.io liquidation feed: {self.ws_url}")

        try:
            async with websockets.connect(
                self.ws_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout
            ) as ws:
                self.ws = ws
                logger.info("✅ Connected to Gate.io liquidation feed")
                self._current_delay = self.reconnect_delay

                # Subscribe to public liquidation channel
                await self._subscribe()

                # Listen for messages
                async for message in ws:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling Gate.io liquidation message: {e}")

        except ConnectionClosed:
            logger.warning("Gate.io liquidation WebSocket connection closed")
        except OSError as e:
            # DNS or network errors - use longer delay
            if "nodename nor servname provided" in str(e) or "Name or service not known" in str(e):
                logger.warning(f"Gate.io DNS/network error (will retry with longer delay): {e}")
                self._current_delay = min(self._current_delay * 4, self.max_reconnect_delay)
            else:
                logger.error(f"Gate.io OS error: {e}")
        except Exception as e:
            logger.error(f"Gate.io connection error: {e}")

    async def _subscribe(self):
        """Subscribe to public liquidation events."""
        # Subscribe to all contracts using '!all' parameter
        # Gate.io format: {"time": timestamp, "channel": "...", "event": "subscribe", "payload": [...]}
        subscription = {
            "time": int(datetime.now().timestamp()),
            "channel": "futures.public_liquidates",
            "event": "subscribe",
            "payload": ["!all"]  # Subscribe to all contracts
        }

        if self.ws:
            try:
                await self.ws.send(json.dumps(subscription))
                logger.info("Subscribed to Gate.io public liquidations (all contracts)")
            except Exception as e:
                logger.error(f"Error subscribing to Gate.io: {e}")

    async def _handle_message(self, message: str):
        """Parse and route incoming liquidation messages."""
        try:
            data = json.loads(message)

            # Handle subscription response
            if data.get("event") == "subscribe":
                if data.get("error") is None:
                    logger.info(f"✅ Gate.io liquidation subscription confirmed")
                else:
                    logger.error(f"❌ Gate.io subscription failed: {data.get('error')}")
                return

            # Handle liquidation updates
            if data.get("channel") == "futures.public_liquidates" and data.get("event") == "update":
                await self._handle_liquidation(data)

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode Gate.io message: {message}")
        except Exception as e:
            logger.error(f"Error handling Gate.io message: {e}")

    async def _handle_liquidation(self, data: dict):
        """Handle liquidation event from Gate.io."""
        try:
            # Gate.io format: {"time": ..., "channel": "...", "event": "update", "result": [...]}
            liquidations = data.get("result", [])

            # Sometimes result might be a dict or other type, ensure it's a list
            if not isinstance(liquidations, list):
                logger.debug(f"Gate.io result is not a list: {type(liquidations)}, data: {data}")
                return

            for liq_data in liquidations:
                # Ensure liq_data is a dict
                if not isinstance(liq_data, dict):
                    logger.warning(f"Gate.io liquidation item is not a dict: {type(liq_data)}, value: {liq_data}")
                    continue

                # Extract fields from Gate.io format
                contract = liq_data.get("contract", "")  # Contract name (e.g., "BTC_USDT")
                size = abs(float(liq_data.get("size", 0)))  # Position size (can be negative)
                price = float(liq_data.get("price", 0))  # Liquidation price
                timestamp_ms = int(liq_data.get("time_ms", 0))  # Timestamp in milliseconds

                # Determine direction from size (negative = short, positive = long)
                raw_size = float(liq_data.get("size", 0))
                direction = "short" if raw_size < 0 else "long"

                # Calculate notional value
                notional_usd = size * price

                # Create liquidation event
                liquidation = LiquidationEvent(
                    venue="Gate.io",
                    pair=contract,
                    direction=direction,
                    size=size,
                    notional_usd=notional_usd,
                    liquidation_price=price,
                    address=None,  # Gate.io doesn't provide user address
                    tx_hash=None,
                    timestamp=datetime.fromtimestamp(timestamp_ms / 1000) if timestamp_ms else datetime.utcnow()
                )

                logger.debug(f"Gate.io liquidation: {contract} {direction} ${notional_usd:,.0f}")

                if self.on_liquidation:
                    asyncio.create_task(self.on_liquidation(liquidation))

        except Exception as e:
            logger.error(f"Error parsing Gate.io liquidation: {e}")
            logger.debug(f"Data: {data}")


class MultiExchangeLiquidationWS:
    """
    Aggregator for multiple exchange liquidation feeds.
    Manages connections to Binance, Bybit, Gate.io, and other exchanges.
    Provides unified liquidation monitoring across major CEX venues.
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
        self.gateio = GateIOLiquidationWS(
            reconnect_delay, max_reconnect_delay, ping_interval, ping_timeout
        )

        # Callback handler
        self.on_liquidation: Optional[Callable] = None

    async def start(self):
        """Start all exchange WebSocket connections."""
        # Set callbacks
        self.binance.on_liquidation = self.on_liquidation
        self.bybit.on_liquidation = self.on_liquidation
        self.gateio.on_liquidation = self.on_liquidation

        # Start connections in parallel
        logger.info("Starting multi-exchange liquidation monitoring...")
        logger.info("Active venues: Binance, Bybit, Gate.io")
        await asyncio.gather(
            self.binance.start(),
            self.bybit.start(),
            self.gateio.start(),
        )

    async def stop(self):
        """Stop all exchange WebSocket connections."""
        logger.info("Stopping multi-exchange liquidation monitoring...")
        await asyncio.gather(
            self.binance.stop(),
            self.bybit.stop(),
            self.gateio.stop(),
        )
