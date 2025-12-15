"""
Format EVM events for Telegram notifications.
Handles token transfers, contract deployments, and address activity.
"""
from datetime import datetime
from typing import Optional
from core.evm_models import EVMTransferEvent, EVMTransactionEvent, TrackedAddress


# Known DEX router addresses
DEX_ROUTERS = {
    '0x7a250d5630b4cf539739df2c5dacb4c659f2488d': '🦄 Uniswap V2 Router',
    '0xe592427a0aece92de3edee1f18e0157c05861564': '🦄 Uniswap V3 Router',
    '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f': '🍣 SushiSwap Router',
    '0x1111111254eeb25477b68fb85ed929f73a960582': '🔄 1inch Router',
    '0xdef1c0ded9bec7f1a1670819833240f027b25eff': '🌊 0x Protocol',
}

# Known CEX deposit addresses
CEX_ADDRESSES = {
    '0x28c6c06298d514db089934071355e5743bf21d60': '🏦 Binance Hot Wallet',
    '0x3f5ce5fbfe3e9af3971dd833d26ba9b5c936f0be': '🏦 Binance Cold Wallet',
    '0x21a31ee1afc51d94c2efccaa2092ad1028285549': '🏦 Binance Deposit',
    '0x46340b20830761efd32832a74d7169b29feb9758': '🏦 Coinbase Deposit',
    '0x503828976d22510aad0201ac7ec88293211d23da': '🏦 Coinbase Cold Storage',
    '0x1151314c646ce4e0efd76d1af4760ae66a9fe30f': '🏦 Kraken Exchange',
}

# LIT-specific addresses
LIT_ADDRESSES = {
    '0x077842a5670cb4c83dca62bda4c36592a5b31891': '🔐 LIT Treasury (Safe)',
    '0x004fe354757574e2deb35fdb304383366f313099': '👤 LIT Deployer',
    '0x232ce3bd40fcd6f80f3d55a522d03f25df784ee2': '📄 LIT Token',
}


def get_address_label(address: str) -> str:
    """Get human-readable label for an address."""
    addr_lower = address.lower()

    # Check LIT-specific addresses first
    if addr_lower in LIT_ADDRESSES:
        return f"{LIT_ADDRESSES[addr_lower]}\n{address[:10]}...{address[-8:]}"

    # Check DEX routers
    if addr_lower in DEX_ROUTERS:
        return f"{DEX_ROUTERS[addr_lower]}\n{address[:10]}...{address[-8:]}"

    # Check CEX addresses
    if addr_lower in CEX_ADDRESSES:
        return f"{CEX_ADDRESSES[addr_lower]}\n{address[:10]}...{address[-8:]}"

    # Check for burn address
    if addr_lower in ['0x0000000000000000000000000000000000000000',
                       '0x000000000000000000000000000000000000dead']:
        return f"🔥 Burn Address\n{address[:10]}...{address[-8:]}"

    # Unknown address
    return f"{address[:10]}...{address[-8:]}"


def shorten_address(address: str) -> str:
    """Shorten an Ethereum address to format: 0xabcd...1234"""
    if len(address) < 10:
        return address
    return f"{address[:6]}...{address[-4:]}"


def is_dex_router(address: str) -> bool:
    """Check if address is a known DEX router."""
    return address.lower() in DEX_ROUTERS


def is_cex_address(address: str) -> bool:
    """Check if address is a known CEX deposit address."""
    return address.lower() in CEX_ADDRESSES


def detect_transfer_type(from_addr: str, to_addr: str, token_symbol: str = "LIT") -> tuple[str, str]:
    """
    Detect the type of transfer and return (emoji, description).

    Returns:
        (emoji, description) - e.g., ("🚀", "LIQUIDITY PROVISION")
    """
    from_lower = from_addr.lower()
    to_lower = to_addr.lower()

    # Burn
    if to_lower in ['0x0000000000000000000000000000000000000000',
                     '0x000000000000000000000000000000000000dead']:
        return ("🔥", "TOKEN BURN (Supply Reduction!)")

    # Mint (from zero address)
    if from_lower == '0x0000000000000000000000000000000000000000':
        return ("🏭", "TOKEN MINT (New Supply)")

    # Treasury outflows
    if from_lower == '0x077842a5670cb4c83dca62bda4c36592a5b31891':
        if is_dex_router(to_addr):
            return ("🚀", "LIQUIDITY PROVISION (Launch Signal!)")
        elif is_cex_address(to_addr):
            return ("📈", "CEX DEPOSIT (Listing Incoming?)")
        else:
            return ("📤", "TREASURY DISTRIBUTION")

    # Deployer activity
    if from_lower == '0x004fe354757574e2deb35fdb304383366f313099':
        return ("👤", "DEPLOYER TRANSFER (Team Movement)")

    # CEX deposit
    if is_cex_address(to_addr):
        return ("⚠️", "CEX DEPOSIT (Potential Sell Pressure)")

    # CEX withdrawal
    if is_cex_address(from_addr):
        return ("💰", "CEX WITHDRAWAL (Accumulation?)")

    # DEX swap
    if is_dex_router(to_addr) or is_dex_router(from_addr):
        return ("🔄", "DEX SWAP")

    # Default transfer
    return ("📦", "TOKEN TRANSFER")


def format_evm_transfer_notification(
    transfer: EVMTransferEvent,
    tracked_address: TrackedAddress
) -> str:
    """
    Format ERC-20 transfer for Telegram notification.

    Example output:
    🚀 LIT LIQUIDITY PROVISION (Launch Signal!)

    💰 Amount: 500,000 LIT ($125,000)
    📤 From: 🔐 LIT Treasury
           0x077842...5B31891
    📥 To: 🦄 Uniswap V2 Router
           0x7a2507...27b25eff

    🔗 Tx: https://etherscan.io/tx/0x1234...5678
    ⏰ 2025-12-13 15:30:45 UTC
    """
    # Detect transfer type
    emoji, description = detect_transfer_type(
        transfer.from_address,
        transfer.to_address,
        transfer.token_symbol or "TOKEN"
    )

    # Format addresses
    from_label = get_address_label(transfer.from_address)
    to_label = get_address_label(transfer.to_address)

    # Format amount
    if transfer.formatted_value is not None:
        amount_str = f"{transfer.formatted_value:,.2f}"
    else:
        # Fallback: convert raw value
        raw_value = int(transfer.raw_value, 16) if transfer.raw_value.startswith('0x') else int(transfer.raw_value)
        formatted = raw_value / (10 ** transfer.decimals)
        amount_str = f"{formatted:,.2f}"

    # Add USD value if available
    usd_str = ""
    if transfer.value_usd and transfer.value_usd > 0:
        usd_str = f" (${transfer.value_usd:,.0f})"

    # Format transaction hash
    tx_short = f"{transfer.tx_hash[:8]}...{transfer.tx_hash[-6:]}"

    # Build message
    symbol = transfer.token_symbol or "TOKEN"
    message = (
        f"{emoji} {symbol} {description}\n\n"
        f"💰 Amount: {amount_str} {symbol}{usd_str}\n"
        f"📤 From: {from_label}\n"
        f"📥 To: {to_label}\n\n"
        f"🔗 Tx: https://etherscan.io/tx/{transfer.tx_hash}\n"
        f"⏰ {transfer.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    # Add context if from tracked address
    if tracked_address.label:
        message = f"🔔 Alert: {tracked_address.label}\n\n" + message

    return message


def format_evm_transaction_notification(
    tx: EVMTransactionEvent,
    tracked_address: TrackedAddress
) -> str:
    """
    Format deployer/treasury transaction for Telegram notification.

    Example output:
    👤 LIT Deployer Activity

    💼 Action: 🏗️ Contract Deployment
    📍 To: New Contract
    💵 Value: 0.5 ETH ($1,200)
    ⛽ Gas: 85.3 gwei

    🔗 Tx: https://etherscan.io/tx/0x1234...5678
    ⏰ 2025-12-13 16:45:22 UTC
    """
    # Determine action type
    if tx.is_contract_creation:
        action = "🏗️ Contract Deployment"
        to_str = "New Contract Created"
    elif tx.method_signature:
        # Try to decode method name
        action = f"⚙️ Contract Call ({tx.method_signature[:10]}...)"
        to_str = get_address_label(tx.to_address) if tx.to_address else "Unknown"
    else:
        action = "📤 Transaction"
        to_str = get_address_label(tx.to_address) if tx.to_address else "Unknown"

    # Format ETH value
    if tx.value_eth is not None:
        eth_str = f"{tx.value_eth:.4f} ETH"
    else:
        # Convert from wei
        value_wei = int(tx.value_wei, 16) if tx.value_wei.startswith('0x') else int(tx.value_wei)
        eth_value = value_wei / 1e18
        eth_str = f"{eth_value:.4f} ETH"

    # Add USD value
    usd_str = ""
    if tx.value_usd and tx.value_usd > 0:
        usd_str = f" (${tx.value_usd:,.0f})"

    # Format transaction hash
    tx_short = f"{tx.tx_hash[:8]}...{tx.tx_hash[-6:]}"

    # Build message
    message = (
        f"🔔 {tracked_address.label} Activity\n\n"
        f"💼 Action: {action}\n"
        f"📍 To: {to_str}\n"
        f"💵 Value: {eth_str}{usd_str}\n"
        f"⛽ Gas: {tx.gas_price_gwei:.1f} gwei\n\n"
        f"🔗 Tx: https://etherscan.io/tx/{tx.tx_hash}\n"
        f"⏰ {tx.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )

    return message


def detect_swap_action(from_addr: str, to_addr: str, token_symbol: str) -> Optional[str]:
    """
    Detect if this is a swap/buy transaction.
    Returns action like "BUY USDT" or "SELL WETH" if detected.
    """
    # Known DEX routers and aggregators
    dex_addresses = [
        '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2 Router
        '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3 Router
        '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad',  # Uniswap Universal Router (V1)
        '0x66a9893cc07d91d95644aedd05d03f95e1dba8af',  # Uniswap V4 Universal Router
        '0x3bf1972f51fb148a3d2acd181188795586f37b98',  # Uniswap Universal Router (another variant)
        '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f',  # SushiSwap Router
        '0x1111111254eeb25477b68fb85ed929f73a960582',  # 1inch V5 Router
        '0xdef1c0ded9bec7f1a1670819833240f027b25eff',  # 0x Protocol Exchange Proxy
    ]

    from_lower = from_addr.lower()
    to_lower = to_addr.lower()

    # If receiving token from DEX = BUY
    if from_lower in dex_addresses:
        return f"BUY {token_symbol}"

    # If sending token to DEX = SELL
    if to_lower in dex_addresses:
        return f"SELL {token_symbol}"

    return None


def format_simple_transfer_alert(
    from_addr: str,
    to_addr: str,
    amount: str,
    token_symbol: str,
    tx_hash: str,
    decimals: int = 18,
    usd_value: Optional[float] = None,
    dex_router: Optional[str] = None,
    wallet_label: Optional[str] = None,
    swap_from_token: Optional[str] = None,
    swap_from_amount: Optional[float] = None,
    swap_from_usd: Optional[float] = None,
    swap_to_token: Optional[str] = None,
    swap_to_amount: Optional[float] = None,
    swap_to_usd: Optional[float] = None
) -> str:
    """
    Enhanced formatter for webhook events with swap detection.
    Used for quick alerts from Alchemy webhooks.

    Args:
        dex_router: The 'to' address from the transaction (DEX router contract)
        wallet_label: Custom label for the tracked wallet address
        swap_from_token: Symbol of the token swapped FROM (e.g., "WETH" for BUY, or "USDT" for SELL)
        swap_from_amount: Amount of the token swapped FROM
        swap_from_usd: USD value of the token swapped FROM
        swap_to_token: Symbol of the token swapped TO (e.g., "ETH" for SELL case)
        swap_to_amount: Amount of the token swapped TO (for SELL case)
        swap_to_usd: USD value of the token swapped TO (for SELL case)
    """
    # Convert amount first
    try:
        raw_amount = int(amount, 16) if amount.startswith('0x') else int(amount)
        formatted_amount = raw_amount / (10 ** decimals)
    except:
        formatted_amount = 0.0

    # Detect if this is a swap - check both transfer addresses AND the transaction's 'to' field
    swap_action = detect_swap_action(from_addr, to_addr, token_symbol)

    # If not detected from transfer addresses, check the DEX router (transaction 'to' field)
    if not swap_action and dex_router:
        # Check if the transaction was sent TO a DEX router
        dex_addresses = [
            '0x7a250d5630b4cf539739df2c5dacb4c659f2488d',  # Uniswap V2 Router
            '0xe592427a0aece92de3edee1f18e0157c05861564',  # Uniswap V3 Router
            '0x3fc91a3afd70395cd496c647d5a6cc9d4b2b7fad',  # Uniswap Universal Router (V1)
            '0x66a9893cc07d91d95644aedd05d03f95e1dba8af',  # Uniswap V4 Universal Router
            '0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f',  # SushiSwap Router
            '0x1111111254eeb25477b68fb85ed929f73a960582',  # 1inch V5 Router
            '0xdef1c0ded9bec7f1a1670819833240f027b25eff',  # 0x Protocol Exchange Proxy
        ]
        if dex_router.lower() in dex_addresses:
            # This is a DEX swap - determine BUY or SELL based on transfer direction
            # If receiving token (from=router), it's a BUY
            # If sending token (to=router), it's a SELL
            if from_addr.lower() in dex_addresses:
                swap_action = f"BUY {token_symbol}"
            else:
                swap_action = f"SELL {token_symbol}"

    if swap_action:
        # Enhanced swap notification (like the external bot)
        # Format: "🟢 BUY USDT (ETHEREUM)"
        emoji = "🟢" if "BUY" in swap_action else "🔴"

        # Show amount with appropriate precision
        # For very small amounts, show more decimals
        if formatted_amount < 0.01:
            amount_str = f"{formatted_amount:.8f}".rstrip('0').rstrip('.')
        elif formatted_amount < 1:
            amount_str = f"{formatted_amount:.6f}".rstrip('0').rstrip('.')
        else:
            amount_str = f"{formatted_amount:,.4f}".rstrip('0').rstrip('.')

        usd_str = f" (${usd_value:,.2f})" if usd_value else ""

        # Get wallet label - use provided label or try to extract from known addresses
        if not wallet_label:
            # Try to extract a simple label from known addresses
            label = get_address_label(from_addr if "SELL" in swap_action else to_addr)
            if not label.startswith("0x"):
                wallet_label = label.split('\n')[0]  # Get first line only
            else:
                wallet_label = "Unknown Wallet"

        # Get user's wallet address (the one doing the swap)
        user_wallet = to_addr if "BUY" in swap_action else from_addr
        wallet_short = f"{user_wallet[:6]}...{user_wallet[-4:]}"

        message = f"{emoji} {swap_action} (ETHEREUM)\n\n"
        message += f"🔹 {wallet_label} ({wallet_short})\n"

        # Check if this is a SELL swap (swap_to is provided)
        if swap_to_token and swap_to_amount is not None:
            # SELL case: User sends current token and receives swap_to token (usually ETH)
            # Format: "swapped X USDT @$Y for Z ETH @$W"

            # Format the FROM amount (token being sold)
            if swap_from_amount < 0.01:
                from_amount_str = f"{swap_from_amount:.8f}".rstrip('0').rstrip('.')
            elif swap_from_amount < 1:
                from_amount_str = f"{swap_from_amount:.6f}".rstrip('0').rstrip('.')
            else:
                from_amount_str = f"{swap_from_amount:,.4f}".rstrip('0').rstrip('.')

            # Format the TO amount (what user receives)
            if swap_to_amount < 0.01:
                to_amount_str = f"{swap_to_amount:.8f}".rstrip('0').rstrip('.')
            elif swap_to_amount < 1:
                to_amount_str = f"{swap_to_amount:.6f}".rstrip('0').rstrip('.')
            else:
                to_amount_str = f"{swap_to_amount:,.4f}".rstrip('0').rstrip('.')

            from_usd_str = f" (${swap_from_usd:,.2f})" if swap_from_usd else ""
            to_usd_str = f" (${swap_to_usd:,.2f})" if swap_to_usd else ""

            # Calculate price per token for FROM token
            from_price_str = ""
            if swap_from_usd and swap_from_amount > 0:
                from_price = swap_from_usd / swap_from_amount
                from_price_str = f" @${from_price:,.2f}"

            # Calculate price per token for TO token
            to_price_str = ""
            if swap_to_usd and swap_to_amount > 0:
                to_price = swap_to_usd / swap_to_amount
                to_price_str = f" @${to_price:,.2f}"

            message += f"swapped {from_amount_str}{from_usd_str} {swap_from_token}{from_price_str} for {to_amount_str}{to_usd_str} {swap_to_token}{to_price_str}\n"

        # If we have swap pair information (BUY case), show the full swap details
        elif swap_from_token and swap_from_amount is not None:
            # BUY case: User sends swap_from token and receives current token
            # Format: "swapped X ETH @$Y for Z USDT @$W"

            # Format the input amount
            if swap_from_amount < 0.01:
                from_amount_str = f"{swap_from_amount:.8f}".rstrip('0').rstrip('.')
            elif swap_from_amount < 1:
                from_amount_str = f"{swap_from_amount:.6f}".rstrip('0').rstrip('.')
            else:
                from_amount_str = f"{swap_from_amount:,.4f}".rstrip('0').rstrip('.')

            from_usd_str = f" (${swap_from_usd:,.2f})" if swap_from_usd else ""
            to_usd_str = f" (${usd_value:,.2f})" if usd_value else ""

            # Calculate price per token for FROM token
            from_price_str = ""
            if swap_from_usd and swap_from_amount > 0:
                from_price = swap_from_usd / swap_from_amount
                from_price_str = f" @${from_price:,.2f}"

            # Calculate price per token for TO token
            to_price_str = ""
            if usd_value and formatted_amount > 0:
                to_price = usd_value / formatted_amount
                to_price_str = f" @${to_price:,.2f}"

            message += f"swapped {from_amount_str}{from_usd_str} {swap_from_token}{from_price_str} for {amount_str}{to_usd_str} {token_symbol}{to_price_str}\n"
        else:
            # Fallback to simple amount display if no swap pair info
            message += f"\n💰 Amount: {amount_str} {token_symbol}{usd_str}\n"

            # Add price per token if USD value available
            if usd_value and formatted_amount > 0:
                price_per_token = usd_value / formatted_amount
                message += f"💵 Price: ${price_per_token:,.2f} per {token_symbol}\n"

        message += f"\n🔗 https://etherscan.io/tx/{tx_hash}"

    else:
        # Standard transfer notification
        emoji, description = detect_transfer_type(from_addr, to_addr, token_symbol)

        # Show amount with appropriate precision
        if formatted_amount < 0.01:
            amount_str = f"{formatted_amount:.8f}".rstrip('0').rstrip('.')
        elif formatted_amount < 1:
            amount_str = f"{formatted_amount:.6f}".rstrip('0').rstrip('.')
        else:
            amount_str = f"{formatted_amount:,.4f}".rstrip('0').rstrip('.')

        usd_str = f" (${usd_value:,.2f})" if usd_value else ""

        # Format addresses
        from_label = get_address_label(from_addr)
        to_label = get_address_label(to_addr)

        message = (
            f"{emoji} {token_symbol} {description}\n\n"
            f"💰 {amount_str} {token_symbol}{usd_str}\n"
            f"📤 From: {from_label}\n"
            f"📥 To: {to_label}\n\n"
            f"🔗 https://etherscan.io/tx/{tx_hash}"
        )

    return message
