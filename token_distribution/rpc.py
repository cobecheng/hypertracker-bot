"""Minimal async JSON-RPC client for EVM token analysis."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import aiohttp

from .chains import EvmChain


SELECTORS = {
    "name": "0x06fdde03",
    "symbol": "0x95d89b41",
    "decimals": "0x313ce567",
    "totalSupply": "0x18160ddd",
    "balanceOf": "0x70a08231",
    "token0": "0x0dfe1681",
    "token1": "0xd21220a7",
}


def address_topic_to_address(topic: str) -> str:
    """Decode an indexed topic into a normalized address."""
    return "0x" + topic[-40:].lower()


def encode_address_call(selector_hex: str, address: str) -> str:
    """Encode a selector + address argument for eth_call."""
    clean = address.lower().replace("0x", "")
    return selector_hex + clean.rjust(64, "0")


def decode_uint256(hex_data: str) -> int:
    """Decode a uint256 return value."""
    if not hex_data or hex_data == "0x":
        return 0
    return int(hex_data, 16)


def decode_string(hex_data: str) -> str | None:
    """Decode a string or bytes32-style token metadata response."""
    if not hex_data or hex_data == "0x":
        return None

    payload = bytes.fromhex(hex_data[2:])
    if not payload:
        return None

    if len(payload) >= 64:
        offset = int.from_bytes(payload[:32], "big")
        if 0 <= offset <= len(payload) - 32:
            length = int.from_bytes(payload[offset:offset + 32], "big")
            start = offset + 32
            end = start + length
            if 0 <= start <= end <= len(payload):
                value = payload[start:end].decode("utf-8", errors="ignore").strip("\x00").strip()
                if value:
                    return value

    value = payload.rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
    return value or None


class RpcError(RuntimeError):
    """Raised when a JSON-RPC request fails."""


class EvmRpcClient:
    """Minimal async RPC wrapper with a small block cache."""

    def __init__(self, chain: EvmChain, rpc_url: str, rpc_source: str):
        self.chain = chain
        self.rpc_url = rpc_url
        self.rpc_source = rpc_source
        self._session: aiohttp.ClientSession | None = None
        self._request_id = 0
        self._block_cache: dict[int, dict[str, Any]] = {}

    async def __aenter__(self) -> "EvmRpcClient":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45))
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()

    async def rpc(self, method: str, params: list[Any]) -> Any:
        """Issue a JSON-RPC request."""
        if self._session is None:
            raise RuntimeError("RPC client session is not initialized")

        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        async with self._session.post(self.rpc_url, json=payload) as response:
            data = await response.json(content_type=None)
            if response.status >= 400:
                raise RpcError(f"{method} failed with HTTP {response.status}: {data}")
            if "error" in data:
                raise RpcError(f"{method} failed: {data['error']}")
            return data.get("result")

    async def eth_block_number(self) -> int:
        return int(await self.rpc("eth_blockNumber", []), 16)

    async def eth_get_block_by_number(self, block_number: int) -> dict[str, Any]:
        cached = self._block_cache.get(block_number)
        if cached is not None:
            return cached
        block_hex = hex(block_number)
        block = await self.rpc("eth_getBlockByNumber", [block_hex, False])
        if block is None:
            raise RpcError(f"Block not found: {block_number}")
        self._block_cache[block_number] = block
        return block

    async def block_timestamp(self, block_number: int) -> int:
        block = await self.eth_get_block_by_number(block_number)
        return int(block["timestamp"], 16)

    async def block_by_timestamp(self, target_ts: int) -> int:
        """Return the highest block with timestamp <= target_ts."""
        low = 0
        high = await self.eth_block_number()
        answer = 0
        while low <= high:
            mid = (low + high) // 2
            mid_ts = await self.block_timestamp(mid)
            if mid_ts <= target_ts:
                answer = mid
                low = mid + 1
            else:
                high = mid - 1
        return answer

    async def eth_get_logs(
        self,
        address: str,
        from_block: int,
        to_block: int,
        topics: list[str | None],
        chunk_size: int = 2_000,
    ) -> list[dict[str, Any]]:
        """Fetch logs in chunks and concatenate the results."""
        if from_block > to_block:
            return []

        all_logs: list[dict[str, Any]] = []
        current = from_block
        active_chunk = max(1, chunk_size)

        while current <= to_block:
            end = min(current + active_chunk - 1, to_block)
            params = [{
                "address": address,
                "fromBlock": hex(current),
                "toBlock": hex(end),
                "topics": topics,
            }]
            try:
                logs = await self.rpc("eth_getLogs", params)
                all_logs.extend(logs)
                current = end + 1
            except RpcError:
                if active_chunk <= 1:
                    raise
                active_chunk = max(1, active_chunk // 2)

        return all_logs

    async def eth_get_code(self, address: str) -> str:
        return await self.rpc("eth_getCode", [address, "latest"])

    async def eth_call(self, to_address: str, data: str, block_tag: str = "latest") -> str:
        return await self.rpc("eth_call", [{"to": to_address, "data": data}, block_tag])

    async def safe_eth_call(self, to_address: str, data: str, block_tag: str = "latest") -> str | None:
        try:
            return await self.eth_call(to_address, data, block_tag)
        except RpcError:
            return None

    async def erc20_metadata(self, token_address: str) -> dict[str, Any]:
        name_hex, symbol_hex, decimals_hex, total_supply_hex = await asyncio.gather(
            self.safe_eth_call(token_address, SELECTORS["name"]),
            self.safe_eth_call(token_address, SELECTORS["symbol"]),
            self.safe_eth_call(token_address, SELECTORS["decimals"]),
            self.safe_eth_call(token_address, SELECTORS["totalSupply"]),
        )
        return {
            "name": decode_string(name_hex or "0x"),
            "symbol": decode_string(symbol_hex or "0x"),
            "decimals": decode_uint256(decimals_hex or "0x"),
            "current_total_supply_raw": decode_uint256(total_supply_hex or "0x"),
        }

    async def detect_pool_tokens(self, address: str) -> tuple[str | None, str | None]:
        token0_hex, token1_hex = await asyncio.gather(
            self.safe_eth_call(address, SELECTORS["token0"]),
            self.safe_eth_call(address, SELECTORS["token1"]),
        )
        if not token0_hex or not token1_hex or token0_hex == "0x" or token1_hex == "0x":
            return None, None
        return (
            "0x" + token0_hex[-40:].lower(),
            "0x" + token1_hex[-40:].lower(),
        )


def iso_to_unix_seconds(value: str) -> int:
    """Parse an ISO timestamp into unix seconds."""
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
