"""
Chaos Labs WebSocket client for cross-venue liquidation monitoring.
Provides real-time liquidation data from multiple exchanges.
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


class ChaosLabsWebSocket:
    """
    Auto-reconnecting WebSocket client for Chaos Labs liquidation feed.
    Monitors liquidations across multiple venues (Hyperliquid, Binance, Bybit, OKX, etc.)
    """
    
    def __init__(
        self,
        ws_url: str,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize Chaos Labs WebSocket client."""
        self.ws_url = ws_url
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
                logger.error(f"Chaos Labs WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting to Chaos Labs in {self._current_delay} seconds...")
                    await asyncio.sleep(self._current_delay)
                    self._current_delay = min(self._current_delay * 2, self.max_reconnect_delay)
    
    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info("Chaos Labs WebSocket stopped")
    
    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info(f"Connecting to Chaos Labs WebSocket: {self.ws_url}")
        
        try:
            async with websockets.connect(
                self.ws_url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout
            ) as ws:
                self.ws = ws
                logger.info("Connected to Chaos Labs WebSocket")
                self._current_delay = self.reconnect_delay
                
                # Subscribe to liquidations
                await self._subscribe()
                
                # Listen for messages
                async for message in ws:
                    try:
                        await self._handle_message(message)
                    except Exception as e:
                        logger.error(f"Error handling Chaos Labs message: {e}")
        
        except ConnectionClosed:
            logger.warning("Chaos Labs WebSocket connection closed")
        except Exception as e:
            logger.error(f"Chaos Labs connection error: {e}")
    
    async def _subscribe(self):
        """Subscribe to liquidation events."""
        # Chaos Labs may use different subscription format
        # Adjust based on actual API documentation
        subscription = {
            "action": "subscribe",
            "channel": "liquidations"
        }
        
        if self.ws:
            try:
                await self.ws.send(json.dumps(subscription))
                logger.info("Subscribed to Chaos Labs liquidations")
            except Exception as e:
                logger.error(f"Error subscribing to Chaos Labs: {e}")
    
    async def _handle_message(self, message: str):
        """Parse and route incoming WebSocket messages."""
        try:
            data = json.loads(message)
            
            # Parse liquidation event based on Chaos Labs format
            # Note: Adjust field names based on actual API response
            if "type" in data and data["type"] == "liquidation":
                await self._handle_liquidation(data)
            elif "event" in data and data["event"] == "liquidation":
                await self._handle_liquidation(data.get("data", {}))
            else:
                # Try to parse as direct liquidation data
                await self._handle_liquidation(data)
        
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode Chaos Labs message: {message}")
        except Exception as e:
            logger.error(f"Error handling Chaos Labs message: {e}")
    
    async def _handle_liquidation(self, data: dict):
        """Handle liquidation event."""
        try:
            # Parse liquidation data (adjust field names based on actual API)
            liquidation = LiquidationEvent(
                venue=data.get("venue", data.get("exchange", "Unknown")),
                pair=data.get("pair", data.get("symbol", "")),
                direction=data.get("direction", data.get("side", "")).lower(),
                size=float(data.get("size", data.get("quantity", 0))),
                notional_usd=float(data.get("notional_usd", data.get("notional", 0))),
                liquidation_price=float(data.get("liquidation_price", data.get("price", 0))),
                address=data.get("address", data.get("account")),
                tx_hash=data.get("tx_hash", data.get("transaction_hash")),
                timestamp=self._parse_timestamp(data.get("timestamp", data.get("time")))
            )
            
            if self.on_liquidation:
                asyncio.create_task(self.on_liquidation(liquidation))
        
        except Exception as e:
            logger.error(f"Error parsing Chaos Labs liquidation: {e}")
    
    def _parse_timestamp(self, timestamp) -> datetime:
        """Parse timestamp from various formats."""
        if timestamp is None:
            return datetime.utcnow()
        
        if isinstance(timestamp, int):
            # Assume milliseconds
            if timestamp > 10**12:
                return datetime.fromtimestamp(timestamp / 1000)
            else:
                return datetime.fromtimestamp(timestamp)
        
        if isinstance(timestamp, str):
            try:
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except:
                pass
        
        return datetime.utcnow()


# Fallback: Individual exchange WebSocket clients
# These can be implemented if Chaos Labs is unavailable or lags

class BinanceLiquidationWS:
    """Fallback Binance liquidation WebSocket client."""
    
    def __init__(self):
        self.ws_url = "wss://fstream.binance.com/ws/!forceOrder@arr"
        # Implementation similar to ChaosLabsWebSocket
        pass


class BybitLiquidationWS:
    """Fallback Bybit liquidation WebSocket client."""
    
    def __init__(self):
        self.ws_url = "wss://stream.bybit.com/v5/public/linear"
        # Implementation similar to ChaosLabsWebSocket
        pass


class OKXLiquidationWS:
    """Fallback OKX liquidation WebSocket client."""
    
    def __init__(self):
        self.ws_url = "wss://ws.okx.com:8443/ws/v5/public"
        # Implementation similar to ChaosLabsWebSocket
        pass
