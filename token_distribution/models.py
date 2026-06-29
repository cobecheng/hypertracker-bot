"""Shared data models for token distribution analysis."""
from __future__ import annotations

from dataclasses import dataclass, field


ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class AddressLabel:
    """A known address label used for wallet classification."""

    name: str
    category: str
    note: str = ""


@dataclass(slots=True)
class TransferRecord:
    """Decoded ERC-20 transfer record."""

    tx_hash: str
    block_number: int
    log_index: int
    timestamp: int
    from_address: str
    to_address: str
    raw_amount: int


@dataclass(slots=True)
class NodeState:
    """State tracked for each address in the distribution graph."""

    address: str
    label: str | None = None
    label_category: str | None = None
    note: str | None = None
    discovered_from: str | None = None
    hop: int | None = None
    is_root: bool = False
    is_contract: bool = False
    is_dex_pool: bool = False
    received_raw: int = 0
    sent_raw: int = 0
    root_inflow_raw: int = 0
    transfers_in: int = 0
    transfers_out: int = 0
    first_seen_ts: int | None = None
    last_seen_ts: int | None = None
    unique_senders: set[str] = field(default_factory=set)
    unique_receivers: set[str] = field(default_factory=set)

    @property
    def balance_raw(self) -> int:
        return self.received_raw - self.sent_raw
