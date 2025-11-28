"""
Filtering utilities for wallet events and liquidations.
Determines whether events should trigger notifications based on user preferences.
"""
import logging
from typing import Optional

from core.models import (
    Wallet, WalletFilters, LiquidationFilters, LiquidationEvent,
    HyperliquidFill, NotificationType, OrderType, Direction
)

logger = logging.getLogger(__name__)


def should_notify_fill(fill: HyperliquidFill, wallet: Wallet, global_filters: Optional[WalletFilters] = None) -> bool:
    """
    Check if a fill event should trigger a notification based on wallet filters and global filters.

    Args:
        fill: The fill event from Hyperliquid
        wallet: The wallet configuration with filters
        global_filters: Optional global filters that apply to all wallets for this user

    Returns:
        True if notification should be sent, False otherwise
    """
    filters = wallet.filters
    
    # Check if notifications are enabled
    if not filters.notifications_enabled:
        return False
    
    # Determine notification type
    is_liquidation = fill.liquidation
    is_close = fill.closed_pnl is not None
    
    if is_liquidation:
        if NotificationType.LIQUIDATION not in filters.notify_on:
            return False
    elif is_close:
        if NotificationType.CLOSE not in filters.notify_on:
            return False
    else:
        # Opening position or adding to position
        if NotificationType.FILL not in filters.notify_on and NotificationType.OPEN not in filters.notify_on:
            return False
    
    # Check asset filter
    if filters.assets is not None and len(filters.assets) > 0:
        if fill.coin not in filters.assets:
            return False
    
    # Check order type (spot vs perp)
    # Note: Hyperliquid API should indicate if it's spot or perp
    # For now, we assume all are perps unless specified otherwise
    # This may need adjustment based on actual API response
    
    # Check direction filter
    if filters.direction != Direction.BOTH:
        # "A" = ask/sell, "B" = bid/buy
        is_long = fill.side == "B"
        is_short = fill.side == "A"
        
        if filters.direction == Direction.LONG and not is_long:
            return False
        if filters.direction == Direction.SHORT and not is_short:
            return False
    
    # Check minimum notional size
    try:
        price = float(fill.px)
        size = float(fill.sz)
        notional = price * size

        if notional < filters.min_notional_usd:
            return False
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse fill price/size: {fill.px}/{fill.sz}")
        return False

    # Apply global filters if they exist
    if global_filters:
        # Global asset filter (more restrictive)
        if global_filters.assets is not None and len(global_filters.assets) > 0:
            if fill.coin not in global_filters.assets:
                logger.info(f"Global filter blocked: {fill.coin} not in allowed assets {global_filters.assets}")
                return False

        # Global direction filter
        if global_filters.direction != Direction.BOTH:
            is_long = fill.side == "B"
            is_short = fill.side == "A"

            if global_filters.direction == Direction.LONG and not is_long:
                logger.info(f"Global filter blocked: direction is {fill.side}, required LONG")
                return False
            if global_filters.direction == Direction.SHORT and not is_short:
                logger.info(f"Global filter blocked: direction is {fill.side}, required SHORT")
                return False

        # Global minimum notional (use the higher of wallet or global)
        if notional < global_filters.min_notional_usd:
            logger.info(f"Global filter blocked: notional ${notional:.2f} < required ${global_filters.min_notional_usd:.2f}")
            return False

    return True


def should_notify_liquidation(liq: LiquidationEvent, filters: LiquidationFilters) -> bool:
    """
    Check if a liquidation event should trigger a notification.
    
    Args:
        liq: The liquidation event
        filters: User's liquidation filters
    
    Returns:
        True if notification should be sent, False otherwise
    """
    # Check if liquidation monitoring is enabled
    if not filters.enabled:
        return False
    
    # Check venue filter
    if liq.venue not in filters.venues:
        return False
    
    # Check pair filter
    if filters.pairs is not None and len(filters.pairs) > 0:
        # Check if any filter matches (support wildcards)
        if "*" not in filters.pairs:
            # Normalize pair format (remove -PERP, -USDT suffixes for comparison)
            pair_base = liq.pair.split('-')[0].split('/')[0].upper()
            filter_matched = False
            
            for filter_pair in filters.pairs:
                filter_base = filter_pair.split('-')[0].split('/')[0].upper()
                if pair_base == filter_base:
                    filter_matched = True
                    break
            
            if not filter_matched:
                return False
    
    # Check minimum notional size
    if liq.notional_usd < filters.min_notional_usd:
        return False
    
    return True


def format_address(address: str, length: int = 6) -> str:
    """
    Format blockchain address for display (0x1234...abcd).
    
    Args:
        address: Full blockchain address
        length: Number of characters to show on each side
    
    Returns:
        Formatted address string
    """
    if not address or len(address) <= length * 2:
        return address
    
    return f"{address[:length]}...{address[-length:]}"


def parse_wallet_addresses(text: str) -> list[str]:
    """
    Parse multiple wallet addresses from user input.
    Supports comma and newline separation.
    
    Args:
        text: User input containing one or more addresses
    
    Returns:
        List of cleaned addresses
    """
    # Split by comma and newline
    addresses = []
    for line in text.replace(',', '\n').split('\n'):
        addr = line.strip()
        if addr:
            addresses.append(addr)
    
    return addresses
