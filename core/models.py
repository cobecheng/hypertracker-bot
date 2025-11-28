"""
Pydantic models for HyperTracker Bot data structures.
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class OrderType(str, Enum):
    """Order type enumeration."""
    SPOT = "spot"
    PERP = "perp"
    BOTH = "both"


class Direction(str, Enum):
    """Trade direction enumeration."""
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class NotificationType(str, Enum):
    """Notification type enumeration."""
    OPEN = "open"
    CLOSE = "close"
    FILL = "fill"
    LIQUIDATION = "liquidation"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"


class WalletFilters(BaseModel):
    """Per-wallet notification filters."""
    notifications_enabled: bool = True
    notify_on: List[NotificationType] = Field(default_factory=lambda: list(NotificationType))
    assets: Optional[List[str]] = None  # None = all assets
    order_type: OrderType = OrderType.BOTH
    min_notional_usd: float = 0.0
    direction: Direction = Direction.BOTH


class Wallet(BaseModel):
    """Wallet tracking model."""
    id: Optional[int] = None
    user_id: int
    address: str
    alias: Optional[str] = None
    filters: WalletFilters = Field(default_factory=WalletFilters)
    active: bool = True
    created_at: Optional[datetime] = None


class LiquidationFilters(BaseModel):
    """Liquidation monitoring filters."""
    enabled: bool = False
    venues: List[str] = Field(default_factory=lambda: ["Hyperliquid", "Lighter", "Binance", "Bybit", "OKX", "gTrade"])
    pairs: Optional[List[str]] = None  # None = all pairs
    min_notional_usd: float = 50000.0


class UserSettings(BaseModel):
    """User settings model."""
    telegram_id: int
    username: Optional[str] = None
    liquidation_filters: LiquidationFilters = Field(default_factory=LiquidationFilters)
    global_wallet_filters: Optional[WalletFilters] = None  # Global filters for all wallets
    created_at: Optional[datetime] = None


class HyperliquidFill(BaseModel):
    """Hyperliquid fill/trade event."""
    wallet: str
    coin: str
    side: str  # "A" (ask/sell) or "B" (bid/buy)
    px: str  # price
    sz: str  # size
    time: int  # timestamp in milliseconds
    hash: Optional[str] = None
    fee: Optional[str] = None
    liquidation: bool = False
    closed_pnl: Optional[str] = None
    dir: Optional[str] = None  # Direction from Hyperliquid: "Open Long", "Close Short", etc.
    start_position: Optional[str] = None  # Position before this fill


class HyperliquidDeposit(BaseModel):
    """Hyperliquid deposit event."""
    wallet: str
    usd: str
    time: int
    hash: Optional[str] = None


class HyperliquidWithdrawal(BaseModel):
    """Hyperliquid withdrawal event."""
    wallet: str
    usd: str
    time: int
    hash: Optional[str] = None


class LiquidationEvent(BaseModel):
    """Cross-venue liquidation event."""
    venue: str
    pair: str
    direction: str  # "long" or "short"
    size: float
    notional_usd: float
    liquidation_price: float
    address: Optional[str] = None
    tx_hash: Optional[str] = None
    timestamp: datetime


class BotStats(BaseModel):
    """Bot statistics."""
    total_users: int
    total_wallets: int
    active_wallets: int
    uptime_seconds: float
