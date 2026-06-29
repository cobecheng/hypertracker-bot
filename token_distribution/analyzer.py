"""Historical first-window token distribution analyzer for EVM tokens."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from .chains import get_chain
from .labels import get_known_label
from .models import NodeState, TransferRecord, TRANSFER_EVENT_TOPIC, ZERO_ADDRESS
from .rpc import EvmRpcClient, RpcError, address_topic_to_address, iso_to_unix_seconds
from .sample_projects import TokenProjectConfig


def normalize_address(address: str) -> str:
    """Normalize an EVM address to lowercase."""
    return address.lower()


def scale_amount(raw_amount: int, decimals: int) -> float:
    """Convert raw token units into human-readable decimals."""
    if decimals <= 0:
        return float(raw_amount)
    return raw_amount / (10 ** decimals)


def shorten(address: str) -> str:
    """Create a short address string for dashboard summaries."""
    return f"{address[:8]}...{address[-6:]}"


def ensure_output_dir(project_root: Path) -> Path:
    """Create the token distribution output directory if needed."""
    output_dir = project_root / "data" / "token_distribution"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


class TokenDistributionAnalyzer:
    """Build a first-window token flow graph and summarize holder categories."""

    def __init__(
        self,
        project_config: TokenProjectConfig,
        project_root: Path,
        *,
        whale_threshold_pct: float = 0.005,
        max_code_lookups: int = 1_200,
    ):
        self.project = project_config
        self.project_root = project_root
        self.whale_threshold_pct = whale_threshold_pct
        self.max_code_lookups = max_code_lookups

    async def analyze(self) -> dict:
        """Run the analysis and return a dashboard-ready payload."""
        chain = get_chain(self.project.chain_slug)
        rpc_url, rpc_source = chain.resolve_rpc_url()
        if not rpc_url:
            return {
                **self.project.dashboard_stub(self.project_root),
                "status": "missing_rpc",
                "setup": {
                    "required_env": [f"{'/'.join(chain.rpc_env_vars)} or ALCHEMY_API_KEY"],
                    "recommended_command": f"./.conda-py311/bin/python scripts/analyze_token_distribution.py --project {self.project.slug}",
                    "why_empty": f"No RPC URL was configured for {chain.name}.",
                },
            }

        async with EvmRpcClient(chain=chain, rpc_url=rpc_url, rpc_source=rpc_source) as rpc:
            metadata = await rpc.erc20_metadata(self.project.token_address)

            if self.project.launch_time_iso:
                start_ts = iso_to_unix_seconds(self.project.launch_time_iso)
            else:
                raise ValueError("launch_time_iso is required for the current analyzer flow")

            start_block = await rpc.block_by_timestamp(start_ts)
            end_ts = start_ts + int(timedelta(days=self.project.window_days).total_seconds())
            end_block = await rpc.block_by_timestamp(end_ts)
            latest_block = await rpc.eth_block_number()

            logs = await rpc.eth_get_logs(
                address=self.project.token_address,
                from_block=start_block,
                to_block=end_block,
                topics=[TRANSFER_EVENT_TOPIC],
            )

            transfers = await self._decode_transfers(rpc, logs)
            payload = await self._build_payload(
                rpc=rpc,
                chain=chain,
                metadata=metadata,
                transfers=transfers,
                start_block=start_block,
                end_block=end_block,
                latest_block=latest_block,
                start_ts=start_ts,
                end_ts=end_ts,
                rpc_source=rpc_source,
            )
            return payload

    async def save(self, payload: dict) -> Path:
        """Persist the analysis payload to disk."""
        output_dir = ensure_output_dir(self.project_root)
        output_path = output_dir / f"{self.project.slug}.json"
        output_path.write_text(self._json_dumps(payload), encoding="utf-8")
        return output_path

    async def _decode_transfers(self, rpc: EvmRpcClient, logs: list[dict]) -> list[TransferRecord]:
        """Decode raw transfer logs into normalized transfer records."""
        block_numbers = sorted({int(entry["blockNumber"], 16) for entry in logs})
        timestamps = await self._fetch_block_timestamps(rpc, block_numbers)

        transfers: list[TransferRecord] = []
        for entry in logs:
            topics = entry.get("topics", [])
            if len(topics) < 3:
                continue

            block_number = int(entry["blockNumber"], 16)
            transfers.append(
                TransferRecord(
                    tx_hash=entry["transactionHash"].lower(),
                    block_number=block_number,
                    log_index=int(entry["logIndex"], 16),
                    timestamp=timestamps[block_number],
                    from_address=address_topic_to_address(topics[1]),
                    to_address=address_topic_to_address(topics[2]),
                    raw_amount=int(entry["data"], 16),
                )
            )

        transfers.sort(key=lambda item: (item.block_number, item.log_index))
        return transfers

    async def _fetch_block_timestamps(self, rpc: EvmRpcClient, block_numbers: Iterable[int]) -> dict[int, int]:
        """Fetch block timestamps concurrently with a bounded semaphore."""
        semaphore = asyncio.Semaphore(20)
        results: dict[int, int] = {}

        async def fetch(block_number: int) -> None:
            async with semaphore:
                results[block_number] = await rpc.block_timestamp(block_number)

        await asyncio.gather(*(fetch(block_number) for block_number in block_numbers))
        return results

    async def _build_payload(
        self,
        *,
        rpc: EvmRpcClient,
        chain,
        metadata: dict,
        transfers: list[TransferRecord],
        start_block: int,
        end_block: int,
        latest_block: int,
        start_ts: int,
        end_ts: int,
        rpc_source: str,
    ) -> dict:
        """Assemble the final dashboard payload."""
        decimals = int(metadata.get("decimals") or 18)
        symbol = metadata.get("symbol") or self.project.symbol
        token_name = metadata.get("name") or self.project.display_name
        current_total_supply_raw = int(metadata.get("current_total_supply_raw") or 0)

        discovered_roots = self._discover_roots(transfers)
        roots = [normalize_address(address) for address in (self.project.root_addresses or tuple(discovered_roots))]

        nodes: dict[str, NodeState] = {}
        aggregated_edges: dict[tuple[str, str], dict] = {}
        reachable_addresses: set[str] = set(roots)
        warnings: list[str] = []

        for root in roots:
            node = nodes.setdefault(root, NodeState(address=root))
            node.is_root = True
            node.hop = 0

        minted_raw = 0
        burned_raw = 0

        for transfer in transfers:
            if transfer.from_address == ZERO_ADDRESS:
                minted_raw += transfer.raw_amount
                if transfer.to_address not in reachable_addresses:
                    reachable_addresses.add(transfer.to_address)
                    node = nodes.setdefault(transfer.to_address, NodeState(address=transfer.to_address))
                    node.is_root = transfer.to_address in roots or not self.project.root_addresses
                    node.hop = 0

            if transfer.to_address == ZERO_ADDRESS:
                burned_raw += transfer.raw_amount

            sender_reachable = transfer.from_address in reachable_addresses or transfer.from_address == ZERO_ADDRESS
            if not sender_reachable:
                continue

            sender = nodes.setdefault(transfer.from_address, NodeState(address=transfer.from_address))
            receiver = nodes.setdefault(transfer.to_address, NodeState(address=transfer.to_address))

            if transfer.from_address != ZERO_ADDRESS:
                sender.sent_raw += transfer.raw_amount
                sender.transfers_out += 1
                sender.last_seen_ts = transfer.timestamp
                sender.unique_receivers.add(transfer.to_address)
                if sender.first_seen_ts is None:
                    sender.first_seen_ts = transfer.timestamp

            if transfer.to_address != ZERO_ADDRESS:
                receiver.received_raw += transfer.raw_amount
                receiver.transfers_in += 1
                receiver.last_seen_ts = transfer.timestamp
                receiver.unique_senders.add(transfer.from_address)
                if receiver.first_seen_ts is None:
                    receiver.first_seen_ts = transfer.timestamp

            if transfer.from_address in roots or transfer.from_address == ZERO_ADDRESS:
                receiver.root_inflow_raw += transfer.raw_amount

            sender_hop = sender.hop if sender.hop is not None else 0
            if transfer.to_address != ZERO_ADDRESS:
                receiver_hop = sender_hop if transfer.from_address == ZERO_ADDRESS else sender_hop + 1
                if receiver.hop is None or receiver_hop < receiver.hop:
                    receiver.hop = receiver_hop
                    receiver.discovered_from = None if transfer.from_address == ZERO_ADDRESS else transfer.from_address
                reachable_addresses.add(transfer.to_address)

            edge = aggregated_edges.setdefault(
                (transfer.from_address, transfer.to_address),
                {
                    "from": transfer.from_address,
                    "to": transfer.to_address,
                    "raw_amount": 0,
                    "transfer_count": 0,
                    "first_block": transfer.block_number,
                    "last_block": transfer.block_number,
                    "first_tx_hash": transfer.tx_hash,
                    "last_tx_hash": transfer.tx_hash,
                },
            )
            edge["raw_amount"] += transfer.raw_amount
            edge["transfer_count"] += 1
            edge["last_block"] = transfer.block_number
            edge["last_tx_hash"] = transfer.tx_hash

        if not transfers:
            warnings.append("No transfer logs were found in the configured analysis window.")

        window_end_supply_raw = max(0, minted_raw - burned_raw)
        supply_basis_raw = window_end_supply_raw or current_total_supply_raw or 1
        whale_threshold_raw = max(1, int(supply_basis_raw * self.whale_threshold_pct))

        await self._enrich_nodes(rpc, nodes, supply_basis_raw, whale_threshold_raw)

        positive_holders = [node for node in nodes.values() if node.balance_raw > 0]
        bucket_rows = self._build_buckets(positive_holders, decimals, supply_basis_raw)
        top_holders = self._build_top_holders(positive_holders, decimals, supply_basis_raw, chain.explorer_base_url)
        notable_routes = self._build_notable_routes(nodes, decimals, chain.explorer_base_url)
        largest_transfers = self._build_largest_transfers(transfers, decimals, chain.explorer_base_url)
        edge_rows = self._build_edge_rows(aggregated_edges.values(), nodes, decimals, chain.explorer_base_url)

        roots_balance_raw = sum(node.balance_raw for node in positive_holders if node.is_root)
        non_root_balance_raw = sum(node.balance_raw for node in positive_holders if not node.is_root)
        retail_balance_raw = sum(node.balance_raw for node in positive_holders if self._resolved_category(node) == "retail_like")
        whale_balance_raw = sum(node.balance_raw for node in positive_holders if self._resolved_category(node) == "whale")
        cex_balance_raw = sum(node.balance_raw for node in positive_holders if self._resolved_category(node) == "cex")
        dex_balance_raw = sum(node.balance_raw for node in positive_holders if self._resolved_category(node) == "dex_pool")

        return {
            "status": "complete",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "project": {
                "slug": self.project.slug,
                "display_name": self.project.display_name,
                "symbol": symbol,
                "chain_slug": self.project.chain_slug,
                "chain_name": chain.name,
                "token_address": self.project.token_address,
                "token_name": token_name,
                "window_days": self.project.window_days,
                "launch_time_iso": self.project.launch_time_iso,
                "root_addresses": roots,
                "declared_total_supply": self.project.declared_total_supply,
                "notes": self.project.notes,
                "references": [{"title": ref.title, "url": ref.url} for ref in self.project.references],
                "tags": list(self.project.tags),
            },
            "window": {
                "start_block": start_block,
                "end_block": end_block,
                "latest_block": latest_block,
                "start_time_iso": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
                "end_time_iso": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
            },
            "supply": {
                "decimals": decimals,
                "window_end_supply_raw": str(window_end_supply_raw),
                "window_end_supply": scale_amount(window_end_supply_raw, decimals),
                "current_total_supply_raw": str(current_total_supply_raw),
                "current_total_supply": scale_amount(current_total_supply_raw, decimals),
                "declared_total_supply": self.project.declared_total_supply,
                "minted_in_window_raw": str(minted_raw),
                "burned_in_window_raw": str(burned_raw),
                "supply_basis_raw": str(supply_basis_raw),
                "supply_basis": scale_amount(supply_basis_raw, decimals),
            },
            "summary": {
                "tracked_holders": len(positive_holders),
                "tracked_addresses": len(nodes),
                "transfer_count": len(transfers),
                "roots_balance": scale_amount(roots_balance_raw, decimals),
                "roots_balance_pct": (roots_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "non_root_balance": scale_amount(non_root_balance_raw, decimals),
                "non_root_balance_pct": (non_root_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "retail_like_balance": scale_amount(retail_balance_raw, decimals),
                "retail_like_balance_pct": (retail_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "whale_balance": scale_amount(whale_balance_raw, decimals),
                "whale_balance_pct": (whale_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "cex_balance": scale_amount(cex_balance_raw, decimals),
                "cex_balance_pct": (cex_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "dex_liquidity_balance": scale_amount(dex_balance_raw, decimals),
                "dex_liquidity_balance_pct": (dex_balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "whale_threshold": scale_amount(whale_threshold_raw, decimals),
                "analysis_status": "Heuristic first-window token distribution view",
            },
            "allocation_buckets": bucket_rows,
            "top_holders": top_holders,
            "notable_routes": notable_routes,
            "largest_transfers": largest_transfers,
            "edges": edge_rows,
            "diagnostics": {
                "rpc_source": rpc_source,
                "warnings": warnings,
                "roots_discovered": discovered_roots,
                "label_note": (
                    "Entity labels come from a local registry plus lightweight on-chain heuristics. "
                    "Exchange and market-maker coverage improves as the label file is extended."
                ),
            },
        }

    def _discover_roots(self, transfers: list[TransferRecord]) -> list[str]:
        """Discover likely genesis roots from mint recipients."""
        minted_by_recipient: dict[str, int] = defaultdict(int)
        for transfer in transfers:
            if transfer.from_address == ZERO_ADDRESS and transfer.to_address != ZERO_ADDRESS:
                minted_by_recipient[transfer.to_address] += transfer.raw_amount
        return [address for address, _ in sorted(minted_by_recipient.items(), key=lambda item: item[1], reverse=True)]

    async def _enrich_nodes(
        self,
        rpc: EvmRpcClient,
        nodes: dict[str, NodeState],
        supply_basis_raw: int,
        whale_threshold_raw: int,
    ) -> None:
        """Add labels, contract flags, pool flags, and heuristic categories."""
        candidate_addresses = sorted(
            nodes.values(),
            key=lambda node: (node.balance_raw > 0, node.balance_raw, node.root_inflow_raw),
            reverse=True,
        )
        addresses_to_check = candidate_addresses[: self.max_code_lookups]
        semaphore = asyncio.Semaphore(24)

        async def enrich(node: NodeState) -> None:
            manual_label = get_known_label(self.project.chain_slug, node.address)
            if manual_label:
                node.label = manual_label.name
                node.label_category = manual_label.category
                node.note = manual_label.note

            if node.address == ZERO_ADDRESS:
                return

            async with semaphore:
                try:
                    code = await rpc.eth_get_code(node.address)
                    node.is_contract = code not in {"0x", "0x0"}
                except RpcError:
                    node.note = (node.note or "") + " Unable to fetch contract bytecode."
                    return

                if node.is_contract:
                    token0, token1 = await rpc.detect_pool_tokens(node.address)
                    if token0 and token1 and self.project.token_address in {token0, token1}:
                        node.is_dex_pool = True

            if node.is_root and not node.label:
                node.label = "Genesis Root"
                node.label_category = "root"
                return

            if node.label_category:
                return

            if node.is_dex_pool:
                node.label = node.label or "DEX Pool"
                node.label_category = "dex_pool"
                return

            if node.balance_raw >= whale_threshold_raw and node.balance_raw > 0:
                node.label_category = "whale"
                node.label = node.label or "Whale Candidate"
                return

            if node.is_contract and node.balance_raw > 0:
                node.label_category = "contract"
                node.label = node.label or "Contract Holder"
                return

            if node.balance_raw > 0:
                node.label_category = "retail_like"
                node.label = node.label or "Retail-like Holder"
                return

            if supply_basis_raw and node.root_inflow_raw > 0 and not node.label:
                node.label = "Observed Participant"

        await asyncio.gather(*(enrich(node) for node in addresses_to_check))

        for node in nodes.values():
            if node.is_root and not node.label_category:
                node.label_category = "root"
                node.label = node.label or "Genesis Root"
            elif not node.label_category:
                node.label_category = "unknown"
                node.label = node.label or "Unknown"

    def _resolved_category(self, node: NodeState) -> str:
        """Resolve a display category for a node."""
        if node.is_root:
            return "root"
        return node.label_category or "unknown"

    def _build_buckets(self, holders: list[NodeState], decimals: int, supply_basis_raw: int) -> list[dict]:
        """Summarize end-of-window holdings by bucket."""
        rows: dict[str, dict] = {}
        names = {
            "root": "Roots / Treasury",
            "cex": "Centralized Exchange",
            "dex_pool": "DEX Liquidity Pools",
            "market_maker": "Market Maker",
            "bridge": "Bridge / Omnichain",
            "whale": "Unlabeled Whales",
            "retail_like": "Retail-like EOAs",
            "contract": "Other Contracts",
            "unknown": "Unknown",
        }

        for node in holders:
            category = self._resolved_category(node)
            row = rows.setdefault(
                category,
                {"category": category, "label": names.get(category, category.replace("_", " ").title()), "holders": 0, "raw_balance": 0},
            )
            row["holders"] += 1
            row["raw_balance"] += node.balance_raw

        ordered = sorted(rows.values(), key=lambda item: item["raw_balance"], reverse=True)
        return [
            {
                "category": row["category"],
                "label": row["label"],
                "holders": row["holders"],
                "balance": scale_amount(row["raw_balance"], decimals),
                "balance_pct": (row["raw_balance"] / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "raw_balance": str(row["raw_balance"]),
            }
            for row in ordered
        ]

    def _build_top_holders(
        self,
        holders: list[NodeState],
        decimals: int,
        supply_basis_raw: int,
        explorer_base_url: str,
    ) -> list[dict]:
        """Build the top-holder table."""
        rows = sorted(holders, key=lambda node: node.balance_raw, reverse=True)[:25]
        return [
            {
                "address": node.address,
                "short_address": shorten(node.address),
                "label": node.label,
                "category": self._resolved_category(node),
                "balance": scale_amount(node.balance_raw, decimals),
                "balance_pct": (node.balance_raw / supply_basis_raw) * 100 if supply_basis_raw else 0,
                "root_inflow": scale_amount(node.root_inflow_raw, decimals),
                "hop": node.hop,
                "transfers_in": node.transfers_in,
                "transfers_out": node.transfers_out,
                "explorer_url": f"{explorer_base_url}/address/{node.address}",
            }
            for node in rows
        ]

    def _build_notable_routes(self, nodes: dict[str, NodeState], decimals: int, explorer_base_url: str) -> list[dict]:
        """Highlight noteworthy reached entities and whales."""
        rows = [
            node
            for node in nodes.values()
            if node.address != ZERO_ADDRESS and (node.root_inflow_raw > 0 or node.balance_raw > 0)
        ]
        rows.sort(
            key=lambda node: (
                self._resolved_category(node) in {"cex", "market_maker", "dex_pool", "whale"},
                node.root_inflow_raw,
                node.balance_raw,
            ),
            reverse=True,
        )

        return [
            {
                "address": node.address,
                "label": node.label,
                "category": self._resolved_category(node),
                "hop": node.hop,
                "discovered_from": node.discovered_from,
                "discovered_from_short": shorten(node.discovered_from) if node.discovered_from else None,
                "received_from_roots": scale_amount(node.root_inflow_raw, decimals),
                "end_balance": scale_amount(node.balance_raw, decimals),
                "explorer_url": f"{explorer_base_url}/address/{node.address}",
            }
            for node in rows[:20]
        ]

    def _build_largest_transfers(self, transfers: list[TransferRecord], decimals: int, explorer_base_url: str) -> list[dict]:
        """Return the largest individual transfers in the window."""
        rows = sorted(transfers, key=lambda transfer: transfer.raw_amount, reverse=True)[:20]
        return [
            {
                "tx_hash": transfer.tx_hash,
                "amount": scale_amount(transfer.raw_amount, decimals),
                "from_address": transfer.from_address,
                "to_address": transfer.to_address,
                "from_short": shorten(transfer.from_address),
                "to_short": shorten(transfer.to_address),
                "block_number": transfer.block_number,
                "timestamp_iso": datetime.fromtimestamp(transfer.timestamp, tz=timezone.utc).isoformat(),
                "explorer_url": f"{explorer_base_url}/tx/{transfer.tx_hash}",
            }
            for transfer in rows
        ]

    def _build_edge_rows(self, edges: Iterable[dict], nodes: dict[str, NodeState], decimals: int, explorer_base_url: str) -> list[dict]:
        """Build the top aggregated graph edges."""
        rows = sorted(edges, key=lambda edge: edge["raw_amount"], reverse=True)[:30]
        edge_rows = []
        for edge in rows:
            from_node = nodes.get(edge["from"])
            to_node = nodes.get(edge["to"])
            edge_rows.append(
                {
                    "from_address": edge["from"],
                    "to_address": edge["to"],
                    "from_label": from_node.label if from_node else None,
                    "to_label": to_node.label if to_node else None,
                    "from_category": self._resolved_category(from_node) if from_node else "unknown",
                    "to_category": self._resolved_category(to_node) if to_node else "unknown",
                    "amount": scale_amount(edge["raw_amount"], decimals),
                    "transfer_count": edge["transfer_count"],
                    "first_tx_url": f"{explorer_base_url}/tx/{edge['first_tx_hash']}",
                    "last_tx_url": f"{explorer_base_url}/tx/{edge['last_tx_hash']}",
                }
            )
        return edge_rows

    def _json_dumps(self, payload: dict) -> str:
        """Pretty-print JSON without bringing in a custom serializer dependency."""
        import json

        return json.dumps(payload, indent=2, sort_keys=False)
