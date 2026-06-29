#!/usr/bin/env python3
"""Analyze a token's first-window distribution and save the result for the dashboard."""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from token_distribution import SAMPLE_PROJECTS, TokenDistributionAnalyzer, TokenProjectConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default="based_eth", help="Sample project slug to analyze")
    parser.add_argument("--chain", help="Override chain slug for ad-hoc analysis")
    parser.add_argument("--token", help="Override token contract address for ad-hoc analysis")
    parser.add_argument("--symbol", help="Optional token symbol for ad-hoc analysis")
    parser.add_argument("--name", help="Optional display name for ad-hoc analysis")
    parser.add_argument("--launch-time", help="ISO timestamp to anchor the start block, e.g. 2026-03-30T00:00:00Z")
    parser.add_argument("--window-days", type=int, help="Analysis window length in days")
    parser.add_argument("--root", action="append", default=[], help="Optional genesis/treasury/root address (repeatable)")
    return parser.parse_args()


def build_project_config(args: argparse.Namespace) -> TokenProjectConfig:
    if args.chain or args.token:
        if not args.chain or not args.token or not args.launch_time:
            raise SystemExit("--chain, --token, and --launch-time are required for ad-hoc analysis")

        slug = args.project or "custom_token"
        return TokenProjectConfig(
            slug=slug,
            display_name=args.name or args.symbol or "Custom Token",
            symbol=args.symbol or "TOKEN",
            chain_slug=args.chain,
            token_address=args.token.lower(),
            window_days=args.window_days or 7,
            launch_time_iso=args.launch_time,
            root_addresses=tuple(address.lower() for address in args.root),
        )

    project = SAMPLE_PROJECTS.get(args.project)
    if project is None:
        valid = ", ".join(sorted(SAMPLE_PROJECTS))
        raise SystemExit(f"Unknown project '{args.project}'. Available sample projects: {valid}")

    if args.window_days:
        project = TokenProjectConfig(
            **{**project.__dict__, "window_days": args.window_days},
        )

    if args.root:
        project = TokenProjectConfig(
            **{**project.__dict__, "root_addresses": tuple(address.lower() for address in args.root)},
        )

    if args.launch_time:
        project = TokenProjectConfig(
            **{**project.__dict__, "launch_time_iso": args.launch_time},
        )

    return project


async def main() -> int:
    args = parse_args()
    project = build_project_config(args)
    analyzer = TokenDistributionAnalyzer(project_config=project, project_root=PROJECT_ROOT)
    payload = await analyzer.analyze()
    output_path = await analyzer.save(payload)
    print(f"Saved token distribution analysis to {output_path}")
    print(f"Status: {payload.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
