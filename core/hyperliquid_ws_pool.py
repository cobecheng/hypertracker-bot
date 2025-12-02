"""
WebSocket connection pool for Hyperliquid.
Each user address gets its own WebSocket connection to avoid ambiguity.
"""
import asyncio
import logging
from typing import Dict, Callable, Optional

from core.hyperliquid_ws import HyperliquidWebSocket
from core.models import HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal, HyperliquidTwapOrder

logger = logging.getLogger(__name__)


class HyperliquidWebSocketPool:
    """
    Manages multiple WebSocket connections - one per user address.

    This is necessary because Hyperliquid's WebSocket API doesn't include
    the user address in userEvents messages, making it impossible to multiplex
    multiple users on a single connection.

    IMPORTANT: Hyperliquid API limits to 10 unique user addresses per IP.
    """

    # Hyperliquid API limit: 10 unique users per IP address
    MAX_USERS_PER_IP = 10

    def __init__(
        self,
        ws_url: str,
        rest_url: str,
        reconnect_delay: int = 1,
        max_reconnect_delay: int = 60,
        ping_interval: int = 20,
        ping_timeout: int = 10
    ):
        """Initialize the WebSocket connection pool."""
        self.ws_url = ws_url
        self.rest_url = rest_url
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout

        # Pool of connections: address -> WebSocket client
        self.connections: Dict[str, HyperliquidWebSocket] = {}

        # Callbacks
        self.on_fill: Optional[Callable] = None
        self.on_deposit: Optional[Callable] = None
        self.on_withdrawal: Optional[Callable] = None
        self.on_liquidation: Optional[Callable] = None
        self.on_twap: Optional[Callable] = None

    async def subscribe_wallet(self, address: str):
        """Subscribe to a wallet address. Creates new connection if needed."""
        # Normalize address to lowercase
        address = address.lower()

        if address in self.connections:
            logger.info(f"Wallet {address} already has an active connection")
            return

        # Check API limit: 10 unique users per IP
        if len(self.connections) >= self.MAX_USERS_PER_IP:
            logger.error(
                f"Cannot subscribe to {address}: Hyperliquid API limits to {self.MAX_USERS_PER_IP} "
                f"unique user addresses per IP. Currently tracking {len(self.connections)} addresses."
            )
            raise ValueError(
                f"Hyperliquid API limit reached: Cannot track more than {self.MAX_USERS_PER_IP} "
                f"wallet addresses per IP. Currently tracking: {len(self.connections)}"
            )

        logger.info(f"Creating new WebSocket connection for {address}")

        # Create new WebSocket connection for this address
        ws = HyperliquidWebSocket(
            ws_url=self.ws_url,
            rest_url=self.rest_url,
            reconnect_delay=self.reconnect_delay,
            max_reconnect_delay=self.max_reconnect_delay,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout
        )

        # Set callbacks
        ws.on_fill = self.on_fill
        ws.on_deposit = self.on_deposit
        ws.on_withdrawal = self.on_withdrawal
        ws.on_liquidation = self.on_liquidation
        ws.on_twap = self.on_twap

        # Store connection
        self.connections[address] = ws

        # Start connection and subscribe
        asyncio.create_task(ws.start())

        # Wait a bit for connection to establish, then subscribe
        await asyncio.sleep(0.5)
        await ws.subscribe_wallet(address)

        logger.info(f"Connection created and subscribed for {address}")

    async def unsubscribe_wallet(self, address: str):
        """Unsubscribe from a wallet address and close its connection."""
        # Normalize address to lowercase
        address = address.lower()

        if address not in self.connections:
            logger.warning(f"No connection found for {address}")
            return

        logger.info(f"Closing WebSocket connection for {address}")

        ws = self.connections[address]
        await ws.stop()
        del self.connections[address]

        logger.info(f"Connection closed for {address}")

    async def stop_all(self):
        """Stop all WebSocket connections."""
        logger.info(f"Stopping {len(self.connections)} WebSocket connections...")

        tasks = []
        for address, ws in self.connections.items():
            logger.info(f"Stopping connection for {address}")
            tasks.append(ws.stop())

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self.connections.clear()
        logger.info("All WebSocket connections stopped")

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self.connections)

    def get_subscribed_addresses(self) -> list[str]:
        """Get list of subscribed addresses."""
        return list(self.connections.keys())
