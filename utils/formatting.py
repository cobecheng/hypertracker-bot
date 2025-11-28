"""
Message formatting utilities for beautiful Telegram notifications.
"""
from datetime import datetime
from typing import Optional

from core.models import HyperliquidFill, LiquidationEvent, Wallet
from utils.filters import format_address


def format_fill_notification(fill: HyperliquidFill, wallet: Wallet) -> str:
    """
    Format a fill event into a beautiful Telegram message.

    Args:
        fill: The fill event
        wallet: The wallet configuration (for alias)

    Returns:
        Formatted message string with emojis
    """
    # Determine action type - use dir field for better accuracy
    is_liquidation = fill.liquidation

    # Check if it's a close based on dir field or closed_pnl
    is_close = False
    if fill.dir:
        is_close = "Close" in fill.dir
    elif fill.closed_pnl is not None and fill.closed_pnl != "0.0":
        is_close = True

    if is_liquidation:
        header = "🚨 LIQUIDATION"
    elif is_close:
        header = "CLOSE POSITION"
    else:
        header = "OPEN POSITION"

    # Wallet info - make address clickable for easy copying
    wallet_name = wallet.alias if wallet.alias else format_address(wallet.address)
    # Using backticks makes the address selectable/copyable in Telegram
    wallet_line = f"Wallet: {wallet_name} (`{wallet.address}`)"

    # Determine side and action using Hyperliquid's dir field
    is_buy = fill.side == "B"
    side_emoji = "🟩" if is_buy else "🟥"
    side_text = "Buy" if is_buy else "Sell"

    # Use the dir field from Hyperliquid if available (e.g., "Open Long", "Close Short")
    if fill.dir:
        action = fill.dir

        # Determine if it's a partial or full close
        if "Close" in action:
            try:
                start_pos = float(fill.start_position) if fill.start_position else 0
                fill_size = float(fill.sz)

                # Check if this closes the entire position
                if abs(start_pos) > 0:
                    if abs(fill_size) >= abs(start_pos):
                        action = f"Full {action}"
                    else:
                        action = f"Partial {action}"
            except (ValueError, TypeError):
                pass  # Keep the original action if parsing fails
    else:
        # Fallback if dir is not provided
        if is_close:
            action = "Close Long" if is_buy else "Close Short"
        else:
            action = "Open Long" if is_buy else "Open Short"

    side_line = f"{side_emoji} {side_text} {fill.coin} — {action}"
    
    # Price and size
    try:
        price = float(fill.px)
        size = float(fill.sz)
        notional = price * size
        
        price_line = f"💰 Price: {price:,.4f} USDC"
        size_line = f"📦 Size: {size:,.2f} {fill.coin} (${notional:,.2f})"
    except (ValueError, TypeError):
        price_line = f"💰 Price: {fill.px} USDC"
        size_line = f"📦 Size: {fill.sz} {fill.coin}"
    
    # PNL (if closing)
    pnl_line = ""
    if fill.closed_pnl:
        try:
            pnl = float(fill.closed_pnl)
            pnl_emoji = "🤑" if pnl > 0 else "😭"
            pnl_sign = "+" if pnl > 0 else ""
            
            # Calculate PNL percentage if possible
            if notional > 0:
                pnl_pct = (pnl / notional) * 100
                pnl_line = f"{pnl_emoji} Realized PNL: {pnl_sign}{pnl:,.2f} USDC ({pnl_sign}{pnl_pct:.2f}%)"
            else:
                pnl_line = f"{pnl_emoji} Realized PNL: {pnl_sign}{pnl:,.2f} USDC"
        except (ValueError, TypeError):
            pnl_line = f"🤑 Realized PNL: {fill.closed_pnl} USDC"
    
    # Fee
    fee_line = ""
    if fill.fee:
        try:
            fee = float(fill.fee)
            fee_line = f"💸 Fee: {fee:,.4f} USDC"
        except (ValueError, TypeError):
            fee_line = f"💸 Fee: {fill.fee} USDC"
    
    # Timestamp
    try:
        timestamp = datetime.fromtimestamp(fill.time / 1000)
        time_line = f"🕒 {timestamp.strftime('%d/%m/%Y, %I:%M:%S %p')} UTC"
    except:
        time_line = f"🕒 {fill.time}"
    
    # Links
    tx_link = ""
    if fill.hash:
        tx_link = f"🔗 https://hypurrscan.io/tx/{fill.hash}"

    # Assemble message
    lines = [
        header,
        wallet_line,
        "",
        side_line,
        price_line,
        size_line,
    ]

    if pnl_line:
        lines.append(pnl_line)

    if fee_line:
        lines.append(fee_line)

    lines.append(time_line)

    if tx_link:
        lines.append("")
        lines.append(tx_link)

    return "\n".join(lines)


def format_liquidation_notification(liq: LiquidationEvent) -> str:
    """
    Format a liquidation event into a beautiful Telegram message.
    
    Args:
        liq: The liquidation event
    
    Returns:
        Formatted message string with emojis
    """
    header = "🚨 LARGE LIQUIDATION"
    
    # Pair
    pair_line = f"Pair: {liq.pair}"
    
    # Direction
    is_long = "long" in liq.direction.lower()
    direction_emoji = "🩸" if is_long else "💀"
    direction_text = "Long liquidated" if is_long else "Short liquidated"
    direction_line = f"Direction: {direction_text} {direction_emoji}"
    
    # Size
    size_line = f"Size: {liq.size:,.4f} ({format_usd(liq.notional_usd)})"
    
    # Liquidation price
    price_line = f"Liq Price: ${liq.liquidation_price:,.2f}"
    
    # Venue
    venue_line = f"Venue: {liq.venue}"
    
    # Address
    address_line = ""
    if liq.address:
        address_line = f"Address: {format_address(liq.address)}"
    
    # Transaction
    tx_line = ""
    if liq.tx_hash:
        if liq.venue.lower() == "hyperliquid":
            tx_line = f"Tx → https://hypurrscan.io/tx/{liq.tx_hash}"
        else:
            tx_line = f"Tx: {format_address(liq.tx_hash, 8)}"
    
    # Timestamp
    time_line = f"Time: {liq.timestamp.strftime('%d/%m/%Y %I:%M:%S %p')} UTC"
    
    # Assemble message
    lines = [
        header,
        "",
        pair_line,
        direction_line,
        size_line,
        price_line,
        venue_line,
    ]
    
    if address_line:
        lines.append(address_line)
    
    if tx_line:
        lines.append(tx_line)
    
    lines.extend([
        "",
        time_line,
    ])
    
    return "\n".join(lines)


def format_deposit_notification(wallet: Wallet, amount: str, timestamp: int, tx_hash: Optional[str] = None) -> str:
    """Format a deposit notification."""
    wallet_name = wallet.alias if wallet.alias else format_address(wallet.address)
    
    try:
        amount_float = float(amount)
        amount_str = f"${amount_float:,.2f}"
    except:
        amount_str = f"${amount}"
    
    try:
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%d/%m/%Y, %I:%M:%S %p')
    except:
        time_str = str(timestamp)
    
    lines = [
        "💰 DEPOSIT",
        f"Wallet: {wallet_name} ({format_address(wallet.address)})",
        "",
        f"Amount: {amount_str} USDC",
        f"🕒 {time_str} UTC",
    ]
    
    if tx_hash:
        lines.append("")
        lines.append(f"Tx → https://hypurrscan.io/tx/{tx_hash}")
    
    return "\n".join(lines)


def format_withdrawal_notification(wallet: Wallet, amount: str, timestamp: int, tx_hash: Optional[str] = None) -> str:
    """Format a withdrawal notification."""
    wallet_name = wallet.alias if wallet.alias else format_address(wallet.address)
    
    try:
        amount_float = float(amount)
        amount_str = f"${amount_float:,.2f}"
    except:
        amount_str = f"${amount}"
    
    try:
        dt = datetime.fromtimestamp(timestamp / 1000)
        time_str = dt.strftime('%d/%m/%Y, %I:%M:%S %p')
    except:
        time_str = str(timestamp)
    
    lines = [
        "💸 WITHDRAWAL",
        f"Wallet: {wallet_name} ({format_address(wallet.address)})",
        "",
        f"Amount: {amount_str} USDC",
        f"🕒 {time_str} UTC",
    ]
    
    if tx_hash:
        lines.append("")
        lines.append(f"Tx → https://hypurrscan.io/tx/{tx_hash}")
    
    return "\n".join(lines)


def format_usd(amount: float) -> str:
    """Format USD amount with appropriate suffix (K, M, B)."""
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f}B"
    elif amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    elif amount >= 1_000:
        return f"${amount / 1_000:.2f}K"
    else:
        return f"${amount:.2f}"
