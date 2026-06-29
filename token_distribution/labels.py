"""Known wallet labels used for first-pass holder classification."""
from __future__ import annotations

from .models import AddressLabel, ZERO_ADDRESS


KNOWN_LABELS: dict[str, dict[str, AddressLabel]] = {
    "ethereum": {
        ZERO_ADDRESS: AddressLabel(name="Zero Address", category="system", note="Mint / burn source"),
        "0x28c6c06298d514db089934071355e5743bf21d60": AddressLabel(
            name="Binance Hot Wallet 14",
            category="cex",
            note="Widely used Binance hot wallet label",
        ),
        "0x21a31ee1afc51d94c2efccaa2092ad1028285549": AddressLabel(
            name="Binance Hot Wallet 15",
            category="cex",
            note="Widely used Binance hot wallet label",
        ),
        "0xf977814e90da44bfa03b6295a0616a897441acec": AddressLabel(
            name="Binance Hot Wallet 8",
            category="cex",
            note="Widely used Binance hot wallet label",
        ),
        "0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be": AddressLabel(
            name="Binance Hot Wallet 7",
            category="cex",
            note="Widely used Binance hot wallet label",
        ),
        "0x742d35cc6634c0532925a3b844bc454e4438f44e": AddressLabel(
            name="Bitfinex Wallet",
            category="cex",
            note="Widely used Bitfinex wallet label",
        ),
    },
    "bsc": {
        ZERO_ADDRESS: AddressLabel(name="Zero Address", category="system", note="Mint / burn source"),
    },
}


def get_known_label(chain_slug: str, address: str) -> AddressLabel | None:
    """Return a known label for an address, if present."""
    return KNOWN_LABELS.get(chain_slug, {}).get(address.lower())
