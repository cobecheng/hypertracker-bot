"""
Fixed Hyperliquid WebSocket client matching the actual API format.
Based on official Hyperliquid documentation.
"""
import asyncio
import json
import logging
import ssl
from typing import Callable, Optional, Set
from datetime import datetime

import aiohttp
import websockets
from websockets.exceptions import ConnectionClosed

from core.models import HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal, HyperliquidTwapOrder

logger = logging.getLogger(__name__)


class HyperliquidWebSocket:
    """
    Auto-reconnecting WebSocket client for Hyperliquid.
    Handles user events with correct API format.
    """
    
    def __init__(
        self,
        ws_url: str,
        rest_url: str,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize Hyperliquid WebSocket client."""
        self.ws_url = ws_url
        self.rest_url = rest_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.running = False
        self.subscribed_wallets: Set[str] = set()
        
        # Callback handlers
        self.on_fill: Optional[Callable] = None
        self.on_deposit: Optional[Callable] = None
        self.on_withdrawal: Optional[Callable] = None
        self.on_liquidation: Optional[Callable] = None
        self.on_twap: Optional[Callable] = None
        
        self._current_delay = reconnect_delay
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        """Start the WebSocket connection with auto-reconnect."""
        self.running = True
        self._session = aiohttp.ClientSession()
        
        logger.info("Starting Hyperliquid WebSocket")
        
        while self.running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    logger.info(f"Reconnecting in {self._current_delay} seconds...")
                    await asyncio.sleep(self._current_delay)
                    self._current_delay = min(self._current_delay * 2, self.max_reconnect_delay)
    
    async def stop(self):
        """Stop the WebSocket connection."""
        self.running = False
        if self.ws:
            await self.ws.close()
        if self._session:
            await self._session.close()
        logger.info("Hyperliquid WebSocket stopped")
    
    async def _connect_and_listen(self):
        """Connect to WebSocket and listen for messages."""
        logger.info(f"Connecting to Hyperliquid WebSocket: {self.ws_url}")

        # Create SSL context
        # Note: If you get SSL errors on macOS, run: pip install --upgrade certifi
        # Or run: /Applications/Python\ X.XX/Install\ Certificates.command
        ssl_context = ssl.create_default_context()

        # TEMPORARY FIX for macOS SSL certificate issues
        # TODO: Run the Install Certificates.command to fix properly
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with websockets.connect(
            self.ws_url,
            ssl=ssl_context,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout
        ) as ws:
            self.ws = ws
            logger.info("Connected to Hyperliquid WebSocket")
            self._current_delay = self.reconnect_delay
            
            # Resubscribe to all wallets
            await self._resubscribe()
            
            # Listen for messages
            async for message in ws:
                try:
                    await self._handle_message(message)
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
                    logger.debug(f"Message content: {message}")
    
    async def _resubscribe(self):
        """Resubscribe to all tracked wallets after reconnection."""
        if not self.subscribed_wallets:
            logger.info("No wallets to subscribe to")
            return
            
        logger.info(f"Resubscribing to {len(self.subscribed_wallets)} wallets...")
        for wallet in list(self.subscribed_wallets):
            await self._subscribe_user(wallet)
            logger.info(f"Subscribed to wallet: {wallet}")
    
    async def subscribe_wallet(self, address: str):
        """Subscribe to events for a specific wallet."""
        if address not in self.subscribed_wallets:
            self.subscribed_wallets.add(address)
            if self.ws:
                await self._subscribe_user(address)
                logger.info(f"Subscribed to wallet: {address}")
    
    async def unsubscribe_wallet(self, address: str):
        """Unsubscribe from events for a specific wallet."""
        if address in self.subscribed_wallets:
            self.subscribed_wallets.remove(address)
            if self.ws:
                await self._unsubscribe_user(address)
                logger.info(f"Unsubscribed from wallet: {address}")
    
    async def _subscribe_user(self, address: str):
        """Send subscription message for user events - CORRECT FORMAT."""
        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "userEvents",
                "user": address
            }
        }
        logger.info(f"Sending subscription: {json.dumps(subscription)}")
        await self.ws.send(json.dumps(subscription))
    
    async def _unsubscribe_user(self, address: str):
        """Send unsubscription message for user events."""
        unsubscription = {
            "method": "unsubscribe",
            "subscription": {
                "type": "userEvents",
                "user": address
            }
        }
        await self.ws.send(json.dumps(unsubscription))
    
    async def _handle_message(self, message: str):
        """Parse and route incoming WebSocket messages - CORRECT FORMAT."""
        try:
            data = json.loads(message)

            # Log full message for debugging
            logger.info(f"Received WebSocket message: {json.dumps(data, indent=2)}")

            # Handle subscription response
            if data.get("channel") == "subscriptionResponse":
                logger.info(f"Subscription confirmed: {data.get('data')}")
                return

            # Handle user events - Hyperliquid sends events at the top level
            # The actual format is: {"channel": "user", "data": {"fills": [...]}}
            # We need to extract the user from the channel subscription context

            # Extract user address from the message
            user_address = None
            event_data = data

            # Check if there's a channel field indicating this is a user event
            if data.get("channel") == "user":
                # Data is in the "data" field
                event_data = data.get("data", {})
                # User address might be in the event data
                user_address = event_data.get("user")
            elif "data" in data and isinstance(data["data"], dict):
                # Alternative format: {"channel": "user", "data": {...}}
                event_data = data["data"]
                user_address = event_data.get("user")
            elif "user" in data:
                # Format: {"user": "0x...", "fills": [...]}
                user_address = data.get("user")
                event_data = data

            # If no user address found, check if we can infer from subscriptions
            # For userEvents subscriptions, the fills belong to the subscribed user
            # Since we only subscribe to specific users, we can match by context
            if not user_address and len(self.subscribed_wallets) > 0:
                # This is a temporary workaround - check each fill for oid/hash to match user
                # For now, we'll need to match based on the subscription
                logger.warning(f"No user address in message, subscribed wallets: {list(self.subscribed_wallets)}")

            if "fills" in event_data:
                logger.info(f"Received fills event with {len(event_data['fills'])} fills for user {user_address}")
                await self._handle_fills(event_data, user_address)

            elif "funding" in event_data:
                logger.info("Received funding event")
                # Handle funding if needed

            elif "liquidation" in event_data:
                logger.info("Received liquidation event")
                await self._handle_liquidation_event(event_data["liquidation"])

            elif "twapHistory" in event_data:
                logger.info("Received twapHistory event (TWAP orders)")
                await self._handle_twap_orders(event_data, user_address)

            elif "twapSliceFills" in event_data:
                logger.debug("Received twapSliceFills event (ignoring - only slice fills)")
                # Ignore slice fills - we only want TWAP order placement notifications

            elif "nonUserCancel" in event_data:
                logger.debug("Received nonUserCancel event")
                # Handle non-user cancels if needed

            else:
                # Log unknown message format for debugging
                logger.debug(f"Unknown message format: {list(data.keys())}")

        except json.JSONDecodeError:
            logger.warning(f"Failed to decode message: {message}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            import traceback
            traceback.print_exc()
    
    async def _handle_fills(self, data: dict, user_address: Optional[str] = None):
        """Handle fills from userEvents."""
        fills = data.get("fills", [])

        # If user_address not provided, try to get from data
        if not user_address:
            user_address = data.get("user")

        # If still no user address and we only have one subscription, use that
        if not user_address and len(self.subscribed_wallets) == 1:
            user_address = list(self.subscribed_wallets)[0]
            logger.info(f"No user in message, using single subscribed wallet: {user_address}")
        elif not user_address:
            logger.error(f"No user address found and multiple subscriptions: {self.subscribed_wallets}")
            user_address = "unknown"

        for fill_data in fills:
            try:
                logger.info(f"Processing fill: {fill_data.get('coin')} {fill_data.get('side')} {fill_data.get('sz')} for wallet {user_address}")

                fill = HyperliquidFill(
                    wallet=user_address,
                    coin=fill_data.get("coin", ""),
                    side=fill_data.get("side", ""),
                    px=fill_data.get("px", "0"),
                    sz=fill_data.get("sz", "0"),
                    time=fill_data.get("time", 0),
                    hash=fill_data.get("hash"),
                    fee=fill_data.get("fee"),
                    liquidation=fill_data.get("liquidation") is not None,
                    closed_pnl=fill_data.get("closedPnl"),
                    dir=fill_data.get("dir"),  # Get direction from Hyperliquid
                    start_position=fill_data.get("startPosition")  # Get starting position
                )

                logger.info(f"Fill parsed: {fill.coin} {fill.side} {fill.sz} @ {fill.px} for wallet {fill.wallet}")

                if self.on_fill:
                    asyncio.create_task(self.on_fill(fill))
                else:
                    logger.warning("No on_fill callback registered")

            except Exception as e:
                logger.error(f"Error parsing fill: {e}")
                logger.error(f"Fill data: {fill_data}")
    
    async def _handle_liquidation_event(self, data: dict):
        """Handle liquidation notification."""
        logger.info(f"Liquidation event: {data}")
        if self.on_liquidation:
            asyncio.create_task(self.on_liquidation(data))

    async def _handle_twap_orders(self, data: dict, user_address: Optional[str] = None):
        """Handle TWAP orders from twapHistory events."""
        twap_history = data.get("twapHistory", [])

        for twap_event in twap_history:
            try:
                # Extract state and status from the event
                state = twap_event.get("state", {})
                status_data = twap_event.get("status", {})
                twap_id = twap_event.get("twapId")

                # Get user address from state
                event_user = state.get("user")
                if not event_user:
                    # Fallback to user_address parameter
                    if user_address:
                        event_user = user_address
                    elif len(self.subscribed_wallets) == 1:
                        event_user = list(self.subscribed_wallets)[0]
                    else:
                        logger.warning(f"No user address found in TWAP event: {twap_event}")
                        continue

                logger.info(f"Processing TWAP order: {state.get('coin')} {state.get('side')} {state.get('sz')} for wallet {event_user}")

                # Only notify on "activated" or "terminated" status
                status = status_data.get("status", "")
                if status not in ["activated", "terminated"]:
                    logger.info(f"Skipping TWAP order with status '{status}' (only notifying on 'activated' or 'terminated')")
                    continue

                twap_order = HyperliquidTwapOrder(
                    wallet=event_user,
                    coin=state.get("coin", ""),
                    side=state.get("side", ""),
                    sz=state.get("sz", "0"),
                    time=state.get("time", 0),  # This is in seconds, not milliseconds
                    minutes=state.get("minutes", 0),
                    executed_sz=state.get("executedSz", "0.0"),
                    executed_ntl=state.get("executedNtl", "0.0"),
                    reduce_only=state.get("reduceOnly", False),
                    randomize=state.get("randomize", False),
                    twap_id=twap_id,
                    status=status
                )

                logger.info(f"TWAP order parsed: {twap_order.coin} {twap_order.side} {twap_order.sz} over {twap_order.minutes}m for wallet {twap_order.wallet}")

                if self.on_twap:
                    asyncio.create_task(self.on_twap(twap_order))
                else:
                    logger.warning("No on_twap callback registered")

            except Exception as e:
                logger.error(f"Error parsing TWAP order: {e}")
                logger.error(f"TWAP event: {twap_event}")
                import traceback
                traceback.print_exc()
