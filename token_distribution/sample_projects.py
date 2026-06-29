"""Sample token project configurations for dashboard demos and analysis runs."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class ProjectReference:
    """Reference metadata shown in the dashboard."""

    title: str
    url: str


@dataclass(frozen=True)
class TokenProjectConfig:
    """Project configuration for a token analysis run."""

    slug: str
    display_name: str
    symbol: str
    chain_slug: str
    token_address: str
    window_days: int = 7
    launch_time_iso: str | None = None
    root_addresses: tuple[str, ...] = ()
    declared_total_supply: float | None = None
    notes: str = ""
    references: tuple[ProjectReference, ...] = ()
    tags: tuple[str, ...] = ()

    def output_path(self, project_root: Path) -> Path:
        return project_root / "data" / "token_distribution" / f"{self.slug}.json"

    def dashboard_stub(self, project_root: Path) -> dict:
        return {
            "status": "needs_run",
            "project": {
                "slug": self.slug,
                "display_name": self.display_name,
                "symbol": self.symbol,
                "chain_slug": self.chain_slug,
                "token_address": self.token_address,
                "window_days": self.window_days,
                "launch_time_iso": self.launch_time_iso,
                "root_addresses": list(self.root_addresses),
                "declared_total_supply": self.declared_total_supply,
                "notes": self.notes,
                "references": [{"title": ref.title, "url": ref.url} for ref in self.references],
                "tags": list(self.tags),
                "output_path": str(self.output_path(project_root)),
            },
            "setup": {
                "required_env": [
                    "ETH_RPC_URL or ALCHEMY_API_KEY for Ethereum analysis",
                ],
                "recommended_command": f"./.conda-py311/bin/python scripts/analyze_token_distribution.py --project {self.slug}",
                "why_empty": "No saved analysis JSON was found for this project yet.",
            },
            "summary": {
                "analysis_status": "Awaiting first run",
                "chain_scope": "Single-chain analysis. Multichain OFT supply must be interpreted carefully.",
            },
        }


SAMPLE_PROJECTS: dict[str, TokenProjectConfig] = {
    "based_eth": TokenProjectConfig(
        slug="based_eth",
        display_name="Based Token",
        symbol="BASED",
        chain_slug="ethereum",
        token_address="0x4f2b33840227ddd0e28da8d4185d6fa07adfed87",
        window_days=7,
        launch_time_iso="2026-01-08T09:21:47+00:00",
        root_addresses=("0x1924b8561eef20e70ede628a296175d358be80e5",),
        declared_total_supply=1_000_000_000.0,
        notes=(
            "Ethereum genesis anchor uses the verified contract-creation timestamp from Etherscan: "
            "2026-01-08 09:21:47 UTC. BASED later had a public TGE on 2026-03-30, so genesis-distribution "
            "analysis and trading-launch analysis are two different views. BASED appears to use an omnichain "
            "token design, so Ethereum on-chain supply can differ from the project's disclosed global fixed supply."
        ),
        references=(
            ProjectReference(title="Official site", url="https://based.one/"),
            ProjectReference(title="Litepaper", url="https://litepaper.based.one/"),
            ProjectReference(title="Ethereum contract", url="https://etherscan.io/token/0x4f2b33840227ddd0e28da8d4185d6fa07adfed87"),
            ProjectReference(title="Ethereum contract creation", url="https://etherscan.io/tx/0x71554380fb3ccd559c8e267551d665b2afb3e089b469d59541811958f2543af7"),
        ),
        tags=("ethereum", "oft", "genesis-distribution"),
    ),
    "based_bsc": TokenProjectConfig(
        slug="based_bsc",
        display_name="Based Token",
        symbol="BASED",
        chain_slug="bsc",
        token_address="0x1d28d989f9e3ccb8b15d0cec601734514f958e4d",
        window_days=7,
        launch_time_iso="2026-03-30T10:00:00+00:00",
        root_addresses=("0x1924b8561eef20e70ede628a296175d358be80e5",),
        declared_total_supply=1_000_000_000.0,
        notes=(
            "BSC sample uses the public TGE anchor of 2026-03-30 10:00 UTC and the verified constructor "
            "delegate/admin wallet 0x1924b8561eeF20e70Ede628A296175D358BE80e5 from BscScan. A reliable "
            "archive-capable BSC RPC is still needed to independently confirm the original deployment transaction."
        ),
        references=(
            ProjectReference(title="Official site", url="https://based.one/"),
            ProjectReference(title="Whitepaper", url="https://basedapp.gitbook.io/docs/"),
            ProjectReference(title="BSC contract", url="https://bscscan.com/token/0x1d28d989f9e3ccb8b15d0cec601734514f958e4d"),
        ),
        tags=("bsc", "oft", "tge-distribution"),
    ),
}
