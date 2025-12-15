"""
Alchemy webhook handler for receiving EVM events.
Processes Address Activity webhooks for token transfers and address activity.
"""
import hmac
import hashlib
import json
import logging
from datetime import datetime
from typing import Optional
import aiohttp

from fastapi import APIRouter, Request, HTTPException

from config import get_settings
from core.database import Database
from bot.notifier import Notifier
from utils.evm_formatting import format_simple_transfer_alert

logger = logging.getLogger(__name__)

# Token metadata cache
_token_cache = {}

# Transaction deduplication cache - stores recently processed tx hashes
# Format: {tx_hash: timestamp}
_processed_transactions = {}
_DEDUP_WINDOW_SECONDS = 60  # Keep transactions in cache for 60 seconds

# Transaction activity cache - stores all activities for a transaction across multiple webhooks
# Format: {tx_hash: {'activities': [...], 'timestamp': float, 'processed': bool}}
_transaction_cache = {}
_TX_CACHE_WINDOW_SECONDS = 10  # Wait up to 10 seconds for all activities of a transaction

# FastAPI router for webhook endpoint
fastapi_router = APIRouter()

# Global references (set by main.py)
db: Optional[Database] = None
notifier: Optional[Notifier] = None


async def fetch_token_symbol(token_address: str) -> str:
    """
    Fetch token symbol using Alchemy Token API.
    Caches results to avoid repeated API calls.
    """
    # Check cache first
    if token_address in _token_cache:
        return _token_cache[token_address]['symbol']

    settings = get_settings()

    # If no Alchemy API key, return address as fallback
    if not settings.alchemy_api_key:
        return token_address[:10] + "..."

    try:
        url = f"https://{settings.alchemy_network}.g.alchemy.com/v2/{settings.alchemy_api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "alchemy_getTokenMetadata",
            "params": [token_address]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get('result', {})
                    symbol = result.get('symbol', 'UNKNOWN')
                    decimals = result.get('decimals', 18)

                    # Cache the result
                    _token_cache[token_address] = {
                        'symbol': symbol,
                        'decimals': decimals,
                        'name': result.get('name', '')
                    }

                    logger.debug(f"Fetched token metadata for {token_address}: {symbol}")
                    return symbol
                else:
                    logger.warning(f"Failed to fetch token metadata: {resp.status}")
                    return "UNKNOWN"

    except Exception as e:
        logger.error(f"Error fetching token metadata: {e}")
        return "UNKNOWN"


async def fetch_token_price_usd(token_symbol: str, amount: float) -> Optional[float]:
    """
    Fetch current token price in USD using DeFiLlama API.
    Returns total USD value for the amount.
    """
    try:
        # Map common symbols to their token addresses for price lookup
        token_addresses = {
            'USDT': 'ethereum:0xdac17f958d2ee523a2206206994597c13d831ec7',
            'USDC': 'ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
            'WETH': 'ethereum:0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
            'DAI': 'ethereum:0x6b175474e89094c44da98b954eedeac495271d0f',
            'WBTC': 'ethereum:0x2260fac5e5542a773aa44fbcfedf7c193bc2c599',
        }

        coin_id = token_addresses.get(token_symbol.upper())
        if not coin_id:
            return None

        url = f"https://coins.llama.fi/prices/current/{coin_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    coins = data.get('coins', {})
                    coin_data = coins.get(coin_id, {})
                    price = coin_data.get('price', 0)

                    if price > 0:
                        usd_value = amount * price
                        logger.debug(f"{amount} {token_symbol} = ${usd_value:.2f} @ ${price:.2f}")
                        return usd_value

    except Exception as e:
        logger.debug(f"Could not fetch price for {token_symbol}: {e}")

    return None


async def fetch_transaction_details(tx_hash: str) -> Optional[dict]:
    """
    Fetch full transaction details from Alchemy to detect DEX swaps.
    Returns transaction receipt with all logs/events.
    """
    settings = get_settings()

    if not settings.alchemy_api_key:
        return None

    try:
        url = f"https://{settings.alchemy_network}.g.alchemy.com/v2/{settings.alchemy_api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    result = data.get('result', {})
                    logger.debug(f"Fetched tx receipt for {tx_hash[:10]}...: to={result.get('to', 'unknown')[:10]}...")
                    return result
                else:
                    logger.warning(f"Failed to fetch transaction receipt: {resp.status}")
                    return None

    except Exception as e:
        logger.error(f"Error fetching transaction details: {e}")
        return None


def verify_alchemy_signature(signature: str, body: bytes, signing_key: str) -> bool:
    """
    Verify Alchemy webhook signature using HMAC SHA-256.

    Args:
        signature: Signature from x-alchemy-signature header
        body: Raw request body bytes
        signing_key: Your webhook signing key from Alchemy dashboard

    Returns:
        True if signature is valid
    """
    if not signing_key:
        logger.warning("No Alchemy signing key configured, skipping signature verification")
        return True

    try:
        # Compute expected signature
        expected_signature = hmac.new(
            signing_key.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()

        # Compare signatures (constant-time comparison)
        return hmac.compare_digest(signature, expected_signature)
    except Exception as e:
        logger.error(f"Error verifying Alchemy signature: {e}")
        return False


@fastapi_router.post("/alchemy-webhook")
async def alchemy_webhook_handler(request: Request):
    """
    Receive and process Alchemy webhook events.

    Webhook types:
    - ADDRESS_ACTIVITY: Token transfers, ETH transfers
    - GRAPHQL (future): Custom GraphQL queries
    """
    settings = get_settings()

    # Get signature from header
    signature = request.headers.get("x-alchemy-signature", "")
    body = await request.body()

    # Verify signature
    if not verify_alchemy_signature(signature, body, settings.alchemy_signing_key):
        logger.warning("Invalid Alchemy webhook signature")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse event
    try:
        event = json.loads(body)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse Alchemy webhook body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Log received event
    logger.info(f"Received Alchemy webhook: type={event.get('type')}, "
                f"webhookId={event.get('webhookId')}")
    logger.debug(f"Event data: {json.dumps(event, indent=2)}")

    # Route to appropriate handler
    webhook_type = event.get("type")
    if webhook_type == "ADDRESS_ACTIVITY":
        await handle_address_activity(event)
    else:
        logger.warning(f"Unknown webhook type: {webhook_type}")

    # Return 200 OK to acknowledge receipt
    return {"status": "received", "timestamp": datetime.utcnow().isoformat()}


async def handle_address_activity(event: dict):
    """
    Process ADDRESS_ACTIVITY webhook.

    Note: Alchemy may send multiple webhook events for the same transaction
    (e.g., one for token transfer, one for ETH transfer). We cache activities
    and wait briefly to collect all related activities before processing.

    Event structure:
    {
        "webhookId": "wh_...",
        "id": "whevt_...",
        "createdAt": "2023-01-01T00:00:00.000Z",
        "type": "ADDRESS_ACTIVITY",
        "event": {
            "network": "ETH_MAINNET",
            "activity": [
                {
                    "fromAddress": "0x...",
                    "toAddress": "0x...",
                    "blockNum": "0x...",
                    "hash": "0x...",
                    "value": 0,
                    "asset": "0x...",  # Token contract address
                    "category": "token",  # or "external", "internal"
                    "rawContract": {
                        "value": "0x...",  # Hex amount
                        "address": "0x...",  # Token contract
                        "decimal": "0x12"  # 18 in hex
                    }
                }
            ]
        }
    }
    """
    import time
    import asyncio

    if not db or not notifier:
        logger.error("Database or notifier not initialized")
        return

    event_data = event.get("event", {})
    activity_list = event_data.get("activity", [])

    logger.info(f"Processing {len(activity_list)} activity items")

    current_time = time.time()

    # Clean up old entries from transaction cache
    expired_txs = [tx for tx, data in _transaction_cache.items()
                   if current_time - data['timestamp'] > _TX_CACHE_WINDOW_SECONDS]
    for tx in expired_txs:
        logger.debug(f"Cleaning up expired transaction from cache: {tx[:10]}...")
        del _transaction_cache[tx]

    # Group activities by transaction hash and add to cache
    from collections import defaultdict
    tx_activities = defaultdict(list)
    for activity in activity_list:
        tx_hash = activity.get("hash", "")
        if tx_hash:
            tx_activities[tx_hash].append(activity)

    # Add activities to cache or update existing entries
    for tx_hash, activities in tx_activities.items():
        if tx_hash not in _transaction_cache:
            _transaction_cache[tx_hash] = {
                'activities': activities,
                'timestamp': current_time,
                'processed': False
            }
            logger.debug(f"Added transaction {tx_hash[:10]}... to cache with {len(activities)} activities")
        else:
            # Add new activities to existing cache entry
            existing = _transaction_cache[tx_hash]['activities']
            for activity in activities:
                if activity not in existing:
                    existing.append(activity)
            logger.debug(f"Updated transaction {tx_hash[:10]}... cache, now has {len(existing)} activities")

    # Wait a bit for more activities to arrive (if this is the first activity we've seen)
    # This gives Alchemy time to send related webhook events
    for tx_hash in tx_activities.keys():
        cache_entry = _transaction_cache[tx_hash]

        # Only wait if this transaction has token transfers and hasn't been processed yet
        has_tokens = any(a.get('category') == 'token' for a in cache_entry['activities'])
        if has_tokens and not cache_entry['processed']:
            # Wait 1 second for ETH transfers to arrive
            logger.debug(f"Waiting 1s for additional activities for {tx_hash[:10]}...")
            await asyncio.sleep(1)

    # Process cached transactions
    for tx_hash, cache_entry in list(_transaction_cache.items()):
        if not cache_entry['processed']:
            try:
                all_activities = cache_entry['activities']
                logger.debug(f"Processing {tx_hash[:10]}... with {len(all_activities)} total activities")
                await process_transaction_activities(all_activities)
                cache_entry['processed'] = True
            except Exception as e:
                logger.error(f"Error processing transaction {tx_hash[:10]}...: {e}", exc_info=True)
                logger.debug(f"Activity data: {cache_entry['activities']}")


async def process_transaction_activities(activities: list):
    """
    Process all activities from a single transaction together.
    This allows us to detect swaps where ETH is exchanged for tokens.
    """
    # Find token transfers, ETH transfers, and other event types
    token_transfers = [a for a in activities if a.get("category") == "token"]
    eth_transfers = [a for a in activities if a.get("category") in ["external", "internal"]]

    # Get the transaction hash to fetch full transaction details for approval detection
    tx_hash = None
    for activity in activities:
        if activity.get("hash"):
            tx_hash = activity.get("hash")
            break

    # Process approvals by checking transaction logs if we have a tx hash
    if tx_hash:
        await process_transaction_approvals(tx_hash)

    # Process contract interactions if we have a tx hash
    if tx_hash:
        await process_contract_interactions(tx_hash, activities)

    # Process each token transfer
    for token_activity in token_transfers:
        # Pass the ETH transfers from the same transaction for swap detection
        await process_token_transfer(token_activity, eth_transfers)

    # Process standalone ETH transfers (when no token transfers are present)
    # This catches wallet-to-wallet ETH transfers and gas fee preparation
    if not token_transfers and eth_transfers:
        logger.debug(f"Processing {len(eth_transfers)} standalone ETH transfer(s)")
        for eth_activity in eth_transfers:
            await process_eth_transfer(eth_activity)


async def process_token_transfer(activity: dict, eth_transfers: list = None):
    """
    Process ERC-20/ERC-721/ERC-1155 token transfer.

    Args:
        activity: The token transfer activity from the webhook
        eth_transfers: List of ETH transfer activities from the same transaction (for swap detection)
    """
    import time

    if eth_transfers is None:
        eth_transfers = []

    from_address = activity.get("fromAddress", "").lower()
    to_address = activity.get("toAddress", "").lower()
    tx_hash = activity.get("hash", "")
    block_num = activity.get("blockNum", "0x0")

    # Deduplication: Check if we've already processed this transaction recently
    current_time = time.time()

    # Clean up old entries from cache (older than DEDUP_WINDOW_SECONDS)
    expired_txs = [tx for tx, timestamp in _processed_transactions.items()
                   if current_time - timestamp > _DEDUP_WINDOW_SECONDS]
    for tx in expired_txs:
        del _processed_transactions[tx]

    # Check if this transaction was already processed
    if tx_hash in _processed_transactions:
        logger.info(f"⏭️  Skipping duplicate transaction: {tx_hash[:10]}... (already processed)")
        return

    # Mark this transaction as processed
    _processed_transactions[tx_hash] = current_time

    # Log the full activity for debugging
    logger.debug(f"Full activity data: {json.dumps(activity, indent=2)}")

    # Get token contract details
    raw_contract = activity.get("rawContract", {})
    token_address = raw_contract.get("address", "").lower()

    # Alchemy sends rawValue (hex string) in rawContract
    raw_value = raw_contract.get("rawValue", "0x0")

    # Get decimals - Alchemy now sends as integer, not hex
    decimals_data = raw_contract.get("decimals", raw_contract.get("decimal", 18))

    # Convert decimals (handle both int and hex formats)
    try:
        if isinstance(decimals_data, str):
            decimals = int(decimals_data, 16) if decimals_data.startswith('0x') else int(decimals_data)
        else:
            decimals = int(decimals_data)
    except:
        decimals = 18

    # Get token symbol (prefer from activity metadata)
    asset_info = activity.get("asset", "")

    # Try to extract symbol from asset string (e.g., "USDT" or token address)
    if asset_info and not asset_info.startswith("0x"):
        token_symbol = asset_info
    else:
        # Fetch token symbol from Alchemy API
        token_symbol = await fetch_token_symbol(token_address)

    # Convert raw value to human-readable amount
    try:
        amount_raw = int(raw_value, 16) if raw_value.startswith('0x') else int(raw_value)
        amount_formatted = amount_raw / (10 ** decimals)

        # Debug logging
        logger.debug(f"Raw value: {raw_value}")
        logger.debug(f"Amount raw: {amount_raw}")
        logger.debug(f"Decimals: {decimals}")
        logger.debug(f"Amount formatted: {amount_formatted}")
    except Exception as e:
        logger.error(f"Error converting amount: {e}")
        amount_formatted = 0.0

    logger.info(f"Token transfer: {token_symbol} {amount_formatted:.8f} from {from_address[:10]}... to {to_address[:10]}...")

    # Fetch USD value
    usd_value = await fetch_token_price_usd(token_symbol, amount_formatted)

    # Fetch transaction details to detect DEX swaps
    tx_receipt = await fetch_transaction_details(tx_hash)
    dex_router_address = None
    swap_from_token_addr = None
    swap_from_token_symbol = None
    swap_from_amount_raw = None
    swap_from_amount_formatted = None
    swap_from_usd = None
    swap_to_token_symbol = None
    swap_to_amount_formatted = None
    swap_to_usd = None

    if tx_receipt:
        # The 'to' field in transaction receipt is the contract being called (often a DEX router)
        to_contract = tx_receipt.get('to', '').lower()
        logger.debug(f"Transaction 'to' contract: {to_contract[:10]}...")
        dex_router_address = to_contract

        # Parse all token transfers in the transaction to find the swap pair
        logs = tx_receipt.get('logs', [])
        transfers = []

        # ERC20 Transfer event signature
        TRANSFER_TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'

        for log in logs:
            topics = log.get('topics', [])
            if topics and topics[0] == TRANSFER_TOPIC:
                # This is a Transfer event
                token_addr = log.get('address', '').lower()
                data = log.get('data', '0x0')

                # Extract from/to addresses from topics
                if len(topics) >= 3:
                    from_addr_log = '0x' + topics[1][-40:]  # Last 40 chars (20 bytes)
                    to_addr_log = '0x' + topics[2][-40:]

                    # Amount is in the data field
                    try:
                        amount_hex = data if data.startswith('0x') else '0x' + data
                        amount_int = int(amount_hex, 16)

                        transfers.append({
                            'token': token_addr,
                            'from': from_addr_log.lower(),
                            'to': to_addr_log.lower(),
                            'amount': amount_int
                        })
                    except:
                        pass

        logger.debug(f"Found {len(transfers)} ERC-20 transfers in transaction")

        # NEW SWAP DETECTION LOGIC:
        # Find all transfers involving the tracked wallet (from_address or to_address)
        # A swap has: user sends token A, user receives token B

        user_wallet = from_address if from_address != to_address else to_address

        # Find tokens sent BY the user
        tokens_sent_by_user = []
        for t in transfers:
            if t['from'] == from_address or t['from'] == to_address:
                tokens_sent_by_user.append(t)

        # Find tokens received BY the user
        tokens_received_by_user = []
        for t in transfers:
            if t['to'] == from_address or t['to'] == to_address:
                tokens_received_by_user.append(t)

        logger.debug(f"User sent {len(tokens_sent_by_user)} tokens, received {len(tokens_received_by_user)} tokens")

        # If user sent 1+ tokens and received 1+ tokens, this is likely a swap
        if tokens_sent_by_user and tokens_received_by_user:
            # Find the token pair for the current activity
            # Current activity is either a send or receive
            current_is_send = (from_address == user_wallet)

            if current_is_send:
                # Current token is being SOLD
                # Look for what the user RECEIVED
                for received in tokens_received_by_user:
                    if received['token'] != token_address:  # Different token
                        # Found the swap TO token
                        swap_to_token_addr = received['token']
                        swap_to_amount_raw = received['amount']

                        logger.debug(f"Detected SELL swap: {token_symbol} -> other token {swap_to_token_addr[:10]}...")

                        # Fetch metadata
                        swap_to_token_symbol = await fetch_token_symbol(swap_to_token_addr)

                        # Get decimals
                        if swap_to_token_addr in _token_cache:
                            to_decimals = _token_cache[swap_to_token_addr].get('decimals', 18)
                        else:
                            to_decimals = 18

                        swap_to_amount_formatted = swap_to_amount_raw / (10 ** to_decimals)
                        swap_to_usd = await fetch_token_price_usd(swap_to_token_symbol, swap_to_amount_formatted)

                        # For SELL, also set swap_from to current token
                        swap_from_token_symbol = token_symbol
                        swap_from_amount_formatted = amount_formatted
                        swap_from_usd = usd_value

                        logger.info(f"✅ Detected {token_symbol} -> {swap_to_token_symbol} SELL swap")
                        break
            else:
                # Current token is being BOUGHT
                # Look for what the user SENT
                for sent in tokens_sent_by_user:
                    if sent['token'] != token_address:  # Different token
                        # Found the swap FROM token
                        swap_from_token_addr = sent['token']
                        swap_from_amount_raw = sent['amount']

                        logger.debug(f"Detected BUY swap: other token {swap_from_token_addr[:10]}... -> {token_symbol}")

                        # Fetch metadata
                        swap_from_token_symbol = await fetch_token_symbol(swap_from_token_addr)

                        # Get decimals
                        if swap_from_token_addr in _token_cache:
                            from_decimals = _token_cache[swap_from_token_addr].get('decimals', 18)
                        else:
                            from_decimals = 18

                        swap_from_amount_formatted = swap_from_amount_raw / (10 ** from_decimals)
                        swap_from_usd = await fetch_token_price_usd(swap_from_token_symbol, swap_from_amount_formatted)

                        logger.info(f"✅ Detected {swap_from_token_symbol} -> {token_symbol} BUY swap")
                        break

        # If no swap found yet, check for ETH swaps from the webhook's activity list
        if not swap_from_token_symbol and not swap_to_token_symbol and eth_transfers:
            logger.debug(f"Checking {len(eth_transfers)} ETH transfers for swap detection")
            for eth_activity in eth_transfers:
                eth_from = eth_activity.get("fromAddress", "").lower()
                eth_to = eth_activity.get("toAddress", "").lower()
                eth_value = eth_activity.get("value", 0)  # Already formatted in ETH

                logger.debug(f"ETH transfer: {eth_value} ETH from {eth_from[:10]}... to {eth_to[:10]}...")

                # Case 1: User is RECEIVING the current token (BUY with ETH)
                # User sends ETH and receives token
                if eth_from == to_address and eth_value > 0:
                    swap_from_token_symbol = "ETH"
                    swap_from_amount_formatted = eth_value
                    swap_from_usd = await fetch_token_price_usd("WETH", eth_value)  # Use WETH price for ETH

                    logger.info(f"✅ Detected ETH -> {token_symbol} BUY swap: {eth_value} ETH" +
                              (f" (${swap_from_usd:.2f})" if swap_from_usd else ""))
                    break

                # Case 2: User is SENDING the current token (SELL for ETH)
                # User sends token and receives ETH
                if eth_to == from_address and eth_value > 0:
                    # For SELL, the swap is: current_token -> ETH
                    swap_from_token_symbol = token_symbol  # The token being sold
                    swap_from_amount_formatted = amount_formatted  # Amount of token sold
                    swap_from_usd = usd_value  # USD value of token sold

                    logger.info(f"✅ Detected {token_symbol} -> ETH SELL swap: {amount_formatted} {token_symbol} for {eth_value} ETH")

                    # For SELL swaps, we need to mark this specially so the formatter knows
                    # to swap the display: show as "SELL TOKEN_SYMBOL" with "swapped X TOKEN for Y ETH"
                    # We'll use a special marker in swap_to values
                    swap_to_token_symbol = "ETH"
                    swap_to_amount_formatted = eth_value
                    swap_to_usd = await fetch_token_price_usd("WETH", eth_value)

                    break

    # Find users tracking this token or these addresses
    tracking_users = []

    # Check if anyone is tracking the token contract
    token_trackers = await db.get_users_tracking_evm_address(token_address)
    tracking_users.extend(token_trackers)
    logger.debug(f"Users tracking token contract {token_address[:10]}...: {len(token_trackers)}")

    # Check if anyone is tracking the from address (treasury/deployer)
    from_trackers = await db.get_users_tracking_evm_address(from_address)
    tracking_users.extend(from_trackers)
    logger.debug(f"Users tracking from address {from_address[:10]}...: {len(from_trackers)}")

    # Check if anyone is tracking the to address
    to_trackers = await db.get_users_tracking_evm_address(to_address)
    tracking_users.extend(to_trackers)
    logger.debug(f"Users tracking to address {to_address[:10]}...: {len(to_trackers)}")

    # Remove duplicates
    unique_users = {user.user_id: user for user in tracking_users}

    if not unique_users:
        logger.info(f"⚠️  No users tracking this transfer (token: {token_address[:10]}..., from: {from_address[:10]}..., to: {to_address[:10]}...)")
        logger.info(f"💡 To receive notifications, use: /add_evm_address and add one of these addresses")
        return

    logger.info(f"Found {len(unique_users)} users to notify")

    # Format and send notifications
    for user_id, tracked_addr in unique_users.items():
        try:
            # Create enhanced alert message with proper amounts and USD values
            message = format_simple_transfer_alert(
                from_addr=from_address,
                to_addr=to_address,
                amount=hex(amount_raw) if not raw_value.startswith('0x') else raw_value,
                token_symbol=token_symbol,
                tx_hash=tx_hash,
                decimals=decimals,
                usd_value=usd_value,
                dex_router=dex_router_address,  # Pass the DEX router address for swap detection
                wallet_label=tracked_addr.label,  # Pass the user's custom label for the tracked address
                swap_from_token=swap_from_token_symbol,  # Token swapped FROM
                swap_from_amount=swap_from_amount_formatted,  # Amount swapped FROM
                swap_from_usd=swap_from_usd,  # USD value of token swapped FROM
                swap_to_token=swap_to_token_symbol,  # Token swapped TO (for SELL case)
                swap_to_amount=swap_to_amount_formatted,  # Amount swapped TO (for SELL case)
                swap_to_usd=swap_to_usd  # USD value of token swapped TO (for SELL case)
            )

            # Send notification to CA tracking channel
            await notifier.send_evm_notification(user_id, message)

            logger.info(f"Sent notification to user {user_id}: {amount_formatted:.4f} {token_symbol}" +
                       (f" (${usd_value:.2f})" if usd_value else ""))

        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")


async def process_contract_interactions(tx_hash: str, activities: list):
    """
    Detect and notify about contract interactions (contract calls).

    A contract interaction is when a tracked wallet calls a smart contract's function.
    We skip interactions that are already covered by other handlers:
    - Token transfers (handled by process_token_transfer)
    - ETH transfers to EOAs (handled by process_eth_transfer)
    - Approvals (handled by process_transaction_approvals)
    """
    try:
        settings = get_settings()

        if not settings.alchemy_api_key:
            return

        # Fetch full transaction details
        url = f"https://{settings.alchemy_network}.g.alchemy.com/v2/{settings.alchemy_api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionByHash",
            "params": [tx_hash]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return

                data = await resp.json()
                tx = data.get('result')

                if not tx:
                    return

                from_address = tx.get('from', '').lower()
                to_address = tx.get('to', '').lower()
                input_data = tx.get('input', '0x')
                value = int(tx.get('value', '0x0'), 16)

                # Skip if no contract call (just ETH transfer with no data)
                if input_data == '0x' or len(input_data) <= 2:
                    return

                # Check if from_address is a tracked wallet
                tracked_users = await db.get_users_tracking_evm_address(from_address)

                if not tracked_users:
                    return

                # Check if to_address is a contract (has code)
                code_payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "eth_getCode",
                    "params": [to_address, "latest"]
                }

                async with session.post(url, json=code_payload, timeout=aiohttp.ClientTimeout(total=5)) as code_resp:
                    if code_resp.status != 200:
                        return

                    code_data = await code_resp.json()
                    contract_code = code_data.get('result', '0x')

                    # If no code, it's an EOA (regular wallet), not a contract
                    if contract_code == '0x' or len(contract_code) <= 2:
                        return

                # Extract method signature (first 4 bytes of input data)
                method_sig = input_data[:10] if len(input_data) >= 10 else input_data

                # Get method name from signature (common methods)
                method_name = _get_method_name(method_sig)

                # Skip if this is a transfer or approve (handled elsewhere)
                if method_name.lower() in ['transfer', 'approve', 'transferfrom', 'safetransferfrom']:
                    return

                logger.info(f"🔧 Contract interaction detected: {from_address[:10]}... -> {to_address[:10]}... method={method_name}")

                # Convert ETH value
                value_eth = value / 1e18
                value_usd = None
                if value_eth > 0:
                    value_usd = await fetch_token_price_usd("WETH", value_eth)

                # Send notifications
                for tracked_addr in tracked_users:
                    try:
                        from utils.evm_formatting import get_address_label, shorten_address

                        contract_label = get_address_label(to_address)

                        # Format value if present
                        value_str = ""
                        if value_eth > 0:
                            value_str = f"\nValue: {value_eth:.4f} ETH"
                            if value_usd:
                                value_str += f" (${value_usd:,.2f})"

                        message = (
                            f"🔔 {tracked_addr.label} ({shorten_address(tracked_addr.address)})\n\n"
                            f"🔧 Contract Interaction\n"
                            f"Contract: {contract_label}\n"
                            f"Method: {method_name}{value_str}\n\n"
                            f"🔗 https://etherscan.io/tx/{tx_hash}"
                        )

                        await notifier.send_evm_notification(tracked_addr.user_id, message)
                        logger.info(f"Sent contract interaction notification to user {tracked_addr.user_id}")

                    except Exception as e:
                        logger.error(f"Error sending contract interaction notification: {e}")

    except Exception as e:
        logger.error(f"Error processing contract interactions for tx {tx_hash[:10]}...: {e}")


def _get_method_name(method_sig: str) -> str:
    """Get human-readable method name from 4-byte signature."""
    # Common method signatures
    KNOWN_METHODS = {
        '0xa9059cbb': 'transfer',
        '0x23b872dd': 'transferFrom',
        '0x095ea7b3': 'approve',
        '0x42842e0e': 'safeTransferFrom',
        '0xb88d4fde': 'safeTransferFrom',
        '0x40c10f19': 'mint',
        '0x42966c68': 'burn',
        '0x3593564c': 'execute',  # Uniswap Universal Router
        '0x5ae401dc': 'multicall',
        '0xac9650d8': 'multicall',
        '0x1249c58b': 'mint',
        '0x883164d6': 'increaseLiquidity',
        '0x0c49ccbe': 'decreaseLiquidity',
        '0xfc6f7865': 'collect',
        '0x88316456': 'exactInputSingle',
        '0x414bf389': 'exactOutputSingle',
        '0xdb3e2198': 'exactInput',
        '0xf28c0498': 'exactOutput',
        '0x12aa3caf': 'swap',  # Uniswap V2
        '0x022c0d9f': 'swap',  # Uniswap V2 pair
        '0xf305d719': 'addLiquidityETH',
        '0xe8e33700': 'addLiquidity',
        '0x02751cec': 'removeLiquidity',
        '0xaf2979eb': 'removeLiquidityETH',
        '0x7ff36ab5': 'swapExactETHForTokens',
        '0x18cbafe5': 'swapExactTokensForETH',
        '0x38ed1739': 'swapExactTokensForTokens',
        '0xfb3bdb41': 'swapETHForExactTokens',
        '0x8803dbee': 'swapTokensForExactTokens',
        '0x4a25d94a': 'stake',
        '0x2e1a7d4d': 'withdraw',
        '0xd0e30db0': 'deposit',
        '0x3ccfd60b': 'withdraw',
        '0xa694fc3a': 'stake',
        '0xe2bbb158': 'deposit',
    }

    method_sig_lower = method_sig.lower()
    return KNOWN_METHODS.get(method_sig_lower, method_sig)


async def process_transaction_approvals(tx_hash: str):
    """
    Check transaction logs for ERC-20 Approval events.

    Approval event signature:
    0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925

    Topics:
    - topics[0]: Event signature (Approval)
    - topics[1]: Owner address (indexed)
    - topics[2]: Spender address (indexed)
    - data: Approved amount (uint256)
    """
    # Approval event signature
    APPROVAL_EVENT_SIG = "0x8c5be1e5ebec7d5bd14f71427d1e84f3dd0314c0f7b2291e5b200ac8c7c3b925"

    try:
        settings = get_settings()

        if not settings.alchemy_api_key:
            logger.debug("Alchemy API key not configured, skipping approval detection")
            return

        # Fetch transaction receipt using Alchemy API
        url = f"https://{settings.alchemy_network}.g.alchemy.com/v2/{settings.alchemy_api_key}"

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_getTransactionReceipt",
            "params": [tx_hash]
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    logger.warning(f"Failed to fetch transaction receipt: {resp.status}")
                    return

                data = await resp.json()
                receipt = data.get('result')

                if not receipt:
                    return

                # Process each log looking for Approval events
                for log in receipt.get('logs', []):
                    topics = log.get('topics', [])

                    if not topics or len(topics) < 3:
                        continue

                    # Check if this is an Approval event
                    event_sig = topics[0]
                    if event_sig.lower() != APPROVAL_EVENT_SIG.lower():
                        continue

                    # Parse approval data
                    token_address = log.get('address', '').lower()
                    owner_address = "0x" + topics[1][-40:]  # Last 20 bytes (remove 0x prefix and padding)
                    spender_address = "0x" + topics[2][-40:]  # Last 20 bytes

                    # Decode amount from data field
                    amount_hex = log.get('data', '0x0')
                    amount_raw = int(amount_hex, 16) if amount_hex else 0

                    logger.info(f"📝 Approval detected: owner={owner_address[:10]}... spender={spender_address[:10]}... token={token_address[:10]}...")

                    # Check if any tracked address is the owner (approver)
                    tracked_users = await db.get_users_tracking_evm_address(owner_address.lower())

                    if not tracked_users:
                        continue

                    # Get token info
                    token_symbol = await fetch_token_symbol(token_address)

                    # Get decimals from cache or fetch
                    decimals = 18  # Default
                    if token_address in _token_cache:
                        decimals = _token_cache[token_address].get('decimals', 18)
                    else:
                        # Trigger fetch which will cache it
                        await fetch_token_symbol(token_address)
                        if token_address in _token_cache:
                            decimals = _token_cache[token_address].get('decimals', 18)

                    # Convert amount
                    amount_formatted = amount_raw / (10 ** decimals) if decimals > 0 else amount_raw

                    # Check if this is unlimited approval (2^256 - 1)
                    MAX_UINT256 = 2**256 - 1
                    is_unlimited = amount_raw >= (MAX_UINT256 - 1000)  # Allow some margin

                    # Get USD value for non-unlimited approvals
                    usd_value = None
                    if not is_unlimited and amount_formatted > 0:
                        usd_value = await fetch_token_price_usd(token_symbol, amount_formatted)

                    # Send notifications
                    for tracked_addr in tracked_users:
                        try:
                            from utils.evm_formatting import get_address_label, shorten_address

                            spender_label = get_address_label(spender_address)

                            # Format amount
                            if is_unlimited:
                                amount_str = "UNLIMITED"
                            else:
                                amount_str = f"{amount_formatted:,.4f}"
                                if usd_value:
                                    amount_str += f" (${usd_value:,.2f})"

                            message = (
                                f"🔔 {tracked_addr.label} ({shorten_address(tracked_addr.address)})\n\n"
                                f"✅ Token Approval\n"
                                f"Token: {token_symbol}\n"
                                f"Amount: {amount_str}\n"
                                f"Spender: {spender_label}\n\n"
                                f"🔗 https://etherscan.io/tx/{tx_hash}"
                            )

                            await notifier.send_evm_notification(tracked_addr.user_id, message)
                            logger.info(f"Sent approval notification to user {tracked_addr.user_id}")

                        except Exception as e:
                            logger.error(f"Error sending approval notification: {e}")

    except Exception as e:
        logger.error(f"Error processing approvals for tx {tx_hash[:10]}...: {e}")


async def process_eth_transfer(activity: dict):
    """Process ETH transfer (external or internal)."""
    from_address = activity.get("fromAddress", "").lower()
    to_address = activity.get("toAddress", "").lower()
    tx_hash = activity.get("hash", "")
    value = activity.get("value", 0)  # Alchemy sends this already formatted in ETH

    logger.info(f"ETH transfer: {value} ETH from {from_address[:10]}... to {to_address[:10]}...")

    # Find users tracking these addresses
    tracking_users = []

    from_trackers = await db.get_users_tracking_evm_address(from_address)
    tracking_users.extend(from_trackers)

    to_trackers = await db.get_users_tracking_evm_address(to_address)
    tracking_users.extend(to_trackers)

    unique_users = {user.user_id: user for user in tracking_users}

    if not unique_users:
        return

    # Value is already in ETH from Alchemy webhook
    value_eth = value

    # Fetch USD value
    usd_value = await fetch_token_price_usd("WETH", value_eth)

    # Format and send notifications
    for user_id, tracked_addr in unique_users.items():
        try:
            from utils.evm_formatting import get_address_label, shorten_address

            from_label = get_address_label(from_address)
            to_label = get_address_label(to_address)

            # Format amount with USD value
            amount_str = f"{value_eth:.4f}"
            usd_str = f" (${usd_value:,.2f})" if usd_value else ""

            # Calculate price per ETH if we have USD value
            price_str = ""
            if usd_value and value_eth > 0:
                price_per_eth = usd_value / value_eth
                price_str = f" @${price_per_eth:,.2f}"

            message = (
                f"🔔 {tracked_addr.label} ({shorten_address(tracked_addr.address)})\n\n"
                f"💵 ETH Transfer\n"
                f"Transferred {amount_str}{usd_str} ETH{price_str}\n"
                f"📤 From: {from_label}\n"
                f"📥 To: {to_label}\n\n"
                f"🔗 https://etherscan.io/tx/{tx_hash}"
            )

            await notifier.send_evm_notification(user_id, message)

        except Exception as e:
            logger.error(f"Error sending ETH transfer notification: {e}")
