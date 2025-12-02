"""
Spot asset mapping utilities for Hyperliquid.
Converts spot asset indices (@107) to human-readable names (HYPE).
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)


class SpotAssetMapper:
    """
    Manages mapping between Hyperliquid spot asset indices and names.

    Spot assets are represented as @{index} (e.g., @107 for HYPE).
    This class fetches metadata from Hyperliquid API and caches the mappings.
    """

    def __init__(self, rest_url: str = "https://api.hyperliquid.xyz/info"):
        """Initialize the spot asset mapper."""
        self.rest_url = rest_url
        self._index_to_name: Dict[int, str] = {}  # @107 -> "HYPE"
        self._token_index_to_name: Dict[int, str] = {}  # 150 -> "HYPE"
        self._last_fetch: Optional[datetime] = None
        self._cache_duration = timedelta(hours=1)  # Refresh every hour
        self._session: Optional[aiohttp.ClientSession] = None
        self._fetch_lock = asyncio.Lock()

    async def _ensure_session(self):
        """Ensure aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_metadata(self) -> bool:
        """
        Fetch spot metadata from Hyperliquid API.

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_session()

            async with self._session.post(
                self.rest_url,
                json={"type": "spotMeta"}
            ) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch spot metadata: HTTP {response.status}")
                    return False

                data = await response.json()

                # Parse tokens: index -> name
                tokens = data.get("tokens", [])
                for token in tokens:
                    token_index = token.get("index")
                    token_name = token.get("name")
                    if token_index is not None and token_name:
                        self._token_index_to_name[token_index] = token_name

                # Parse universe (spot pairs): spot index -> pair name
                universe = data.get("universe", [])
                for pair in universe:
                    pair_index = pair.get("index")
                    pair_name = pair.get("name")
                    token_indices = pair.get("tokens", [])

                    if pair_index is None:
                        continue

                    # If name is provided (e.g., "PURR/USDC"), use it
                    if pair_name and not pair_name.startswith("@"):
                        # Extract base token name from pair (e.g., "PURR/USDC" -> "PURR")
                        base_token = pair_name.split("/")[0]
                        self._index_to_name[pair_index] = base_token

                    # Otherwise, derive from token indices
                    elif len(token_indices) >= 2:
                        base_token_idx = token_indices[0]
                        base_token_name = self._token_index_to_name.get(base_token_idx)
                        if base_token_name:
                            self._index_to_name[pair_index] = base_token_name

                self._last_fetch = datetime.now()
                logger.info(f"Loaded {len(self._index_to_name)} spot asset mappings")
                return True

        except Exception as e:
            logger.error(f"Error fetching spot metadata: {e}")
            return False

    async def _maybe_refresh(self):
        """Refresh metadata if cache is stale."""
        if (self._last_fetch is None or
            datetime.now() - self._last_fetch > self._cache_duration):
            async with self._fetch_lock:
                # Double-check after acquiring lock
                if (self._last_fetch is None or
                    datetime.now() - self._last_fetch > self._cache_duration):
                    await self._fetch_metadata()

    async def get_asset_name(self, coin: str) -> str:
        """
        Convert spot asset index to name.

        Args:
            coin: Asset identifier (e.g., "@107" for spot, "BTC" for perp)

        Returns:
            Human-readable asset name (e.g., "HYPE")
            Returns original coin if not a spot asset or mapping not found
        """
        # Not a spot asset
        if not coin.startswith("@"):
            return coin

        # Parse index from @107
        try:
            spot_index = int(coin[1:])
        except ValueError:
            logger.warning(f"Invalid spot asset format: {coin}")
            return coin

        # Ensure metadata is loaded
        await self._maybe_refresh()

        # Return mapped name or original if not found
        return self._index_to_name.get(spot_index, coin)

    async def initialize(self):
        """
        Initialize the mapper by fetching metadata.
        Call this on bot startup for faster first lookups.
        """
        await self._fetch_metadata()


# Global instance
_mapper: Optional[SpotAssetMapper] = None


def get_spot_mapper(rest_url: str = "https://api.hyperliquid.xyz/info") -> SpotAssetMapper:
    """Get or create the global spot asset mapper instance."""
    global _mapper
    if _mapper is None:
        _mapper = SpotAssetMapper(rest_url)
    return _mapper


async def resolve_asset_name(coin: str, rest_url: str = "https://api.hyperliquid.xyz/info") -> str:
    """
    Convenience function to resolve asset name.

    Args:
        coin: Asset identifier (e.g., "@107", "BTC")
        rest_url: Hyperliquid REST API URL

    Returns:
        Human-readable asset name
    """
    mapper = get_spot_mapper(rest_url)
    return await mapper.get_asset_name(coin)
