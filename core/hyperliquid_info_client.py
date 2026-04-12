"""
Hyperliquid info endpoint client for live account snapshots.
"""
import asyncio
import logging
from typing import Any, Optional

import aiohttp

logger = logging.getLogger(__name__)


class HyperliquidInfoClient:
    """Thin async client for Hyperliquid's info endpoint."""

    def __init__(self, rest_url: str):
        self.rest_url = rest_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=10)
            self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_clearinghouse_state(self, user_address: str, dex: str = "") -> dict[str, Any]:
        """Fetch live perpetual account state for a user."""
        await self._ensure_session()

        payload = {
            "type": "clearinghouseState",
            "user": user_address,
        }
        if dex:
            payload["dex"] = dex

        async with self._lock:
            async with self._session.post(self.rest_url, json=payload) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(
                        f"Hyperliquid info request failed for {user_address}"
                        f"{f' on dex {dex}' if dex else ''}: "
                        f"HTTP {response.status} - {body[:200]}"
                    )
                data = await response.json()
                logger.debug("Fetched clearinghouseState for %s on dex %s", user_address, dex or "<default>")
                return data
