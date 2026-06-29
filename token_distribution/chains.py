"""Chain registry and RPC URL resolution for EVM analysis."""
from __future__ import annotations

from dataclasses import dataclass
import os


@dataclass(frozen=True)
class EvmChain:
    slug: str
    name: str
    chain_id: int
    explorer_base_url: str
    alchemy_network: str | None
    rpc_env_vars: tuple[str, ...]

    def resolve_rpc_url(self) -> tuple[str | None, str | None]:
        """Resolve the RPC URL for the chain and return (url, source)."""
        for env_var in self.rpc_env_vars:
            value = os.getenv(env_var)
            if value:
                return value, env_var

        alchemy_key = os.getenv("ALCHEMY_API_KEY")
        if alchemy_key and self.alchemy_network:
            return f"https://{self.alchemy_network}.g.alchemy.com/v2/{alchemy_key}", "ALCHEMY_API_KEY"

        return None, None


CHAINS: dict[str, EvmChain] = {
    "ethereum": EvmChain(
        slug="ethereum",
        name="Ethereum Mainnet",
        chain_id=1,
        explorer_base_url="https://etherscan.io",
        alchemy_network="eth-mainnet",
        rpc_env_vars=("ETH_RPC_URL", "ETHEREUM_RPC_URL"),
    ),
    "bsc": EvmChain(
        slug="bsc",
        name="BNB Smart Chain",
        chain_id=56,
        explorer_base_url="https://bscscan.com",
        alchemy_network=None,
        rpc_env_vars=("BSC_RPC_URL", "BNB_RPC_URL"),
    ),
}


def get_chain(slug: str) -> EvmChain:
    """Get a chain config by slug."""
    chain = CHAINS.get(slug)
    if chain is None:
        raise KeyError(f"Unsupported chain: {slug}")
    return chain
