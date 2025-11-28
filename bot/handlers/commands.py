"""
Command handlers for HyperTracker Bot.
Handles /start, /stats, and other text commands.
"""
import logging
import time
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from bot.keyboards import get_main_menu_keyboard, get_back_to_menu_keyboard
from core.database import Database
from core.models import Wallet, WalletFilters
from utils.filters import parse_wallet_addresses

logger = logging.getLogger(__name__)

router = Router()

# Global references (will be set by main.py)
db: Database = None
start_time: float = time.time()
reload_wallets_callback = None  # Will be set to main app's load_active_wallets method


class AddWalletStates(StatesGroup):
    """States for adding wallet flow."""
    waiting_for_addresses = State()
    waiting_for_alias = State()


class EditWalletStates(StatesGroup):
    """States for editing wallet settings."""
    waiting_for_assets = State()
    waiting_for_min_notional = State()


class EditLiquidationStates(StatesGroup):
    """States for editing liquidation settings."""
    waiting_for_pairs = State()
    waiting_for_min_notional = State()


class EditGlobalFilterStates(StatesGroup):
    """States for editing global filter settings."""
    waiting_for_assets = State()
    waiting_for_min_notional = State()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    
    # Create user in database
    await db.create_user(message.from_user.id, message.from_user.username)
    
    welcome_text = """
🎉 Welcome to HyperTracker Bot!

Track Hyperliquid wallets in real-time and monitor large liquidations across multiple venues.

Features:
• 📊 Real-time wallet tracking with customizable filters
• 🚨 Large liquidation alerts (Hyperliquid, Binance, Bybit, OKX, etc.)
• ⚡ Sub-2-second latency from event to notification
• 🎯 Per-wallet notification settings

Choose an option below to get started:
"""
    
    await message.answer(welcome_text, reply_markup=get_main_menu_keyboard())


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Handle /stats command."""
    stats = await db.get_stats()
    uptime_seconds = time.time() - start_time
    
    # Format uptime
    hours = int(uptime_seconds // 3600)
    minutes = int((uptime_seconds % 3600) // 60)
    
    stats_text = f"""
📊 **Bot Statistics**

👥 Total Users: {stats['total_users']}
📋 Total Wallets: {stats['total_wallets']}
✅ Active Wallets: {stats['active_wallets']}
⏱️ Uptime: {hours}h {minutes}m

Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
"""
    
    await message.answer(stats_text, reply_markup=get_back_to_menu_keyboard())


@router.message(AddWalletStates.waiting_for_addresses)
async def process_wallet_addresses(message: Message, state: FSMContext):
    """Process wallet addresses input."""
    addresses = parse_wallet_addresses(message.text)
    
    if not addresses:
        await message.answer("❌ No valid addresses found. Please try again or /cancel")
        return
    
    # Store addresses in state
    await state.update_data(addresses=addresses)
    
    # Ask for alias
    if len(addresses) == 1:
        await message.answer(
            f"📝 Enter an alias for this wallet (optional):\n\n"
            f"Address: `{addresses[0]}`\n\n"
            f"Type /skip to skip alias.",
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"📝 Found {len(addresses)} addresses. They will be added without aliases.\n\n"
            f"Type /confirm to add them all, or /cancel to abort."
        )
    
    await state.set_state(AddWalletStates.waiting_for_alias)


@router.message(AddWalletStates.waiting_for_alias, F.text == "/skip")
async def skip_alias(message: Message, state: FSMContext):
    """Skip alias and add wallet."""
    data = await state.get_data()
    addresses = data.get('addresses', [])
    
    if len(addresses) == 1:
        await add_wallets(message, addresses, None)
    
    await state.clear()


@router.message(AddWalletStates.waiting_for_alias, F.text == "/confirm")
async def confirm_multiple_wallets(message: Message, state: FSMContext):
    """Confirm adding multiple wallets."""
    data = await state.get_data()
    addresses = data.get('addresses', [])
    
    await add_wallets(message, addresses, None)
    await state.clear()


@router.message(AddWalletStates.waiting_for_alias)
async def process_alias(message: Message, state: FSMContext):
    """Process wallet alias."""
    data = await state.get_data()
    addresses = data.get('addresses', [])
    alias = message.text.strip()
    
    await add_wallets(message, addresses, alias if alias else None)
    await state.clear()


async def add_wallets(message: Message, addresses: list[str], alias: str = None):
    """Add wallets to database."""
    user_id = message.from_user.id
    added = 0
    skipped = 0

    for address in addresses:
        wallet = Wallet(
            user_id=user_id,
            address=address,
            alias=alias if len(addresses) == 1 else None,
            filters=WalletFilters()
        )

        wallet_id = await db.add_wallet(wallet)
        if wallet_id:
            added += 1
        else:
            skipped += 1

    # Reload wallets in main app to subscribe to new addresses
    if added > 0 and reload_wallets_callback:
        logger.info("Reloading wallets after adding new ones...")
        await reload_wallets_callback()

    if added > 0:
        await message.answer(
            f"✅ Added {added} wallet(s) successfully!\n"
            f"{f'⚠️ Skipped {skipped} (already exist)' if skipped > 0 else ''}\n\n"
            f"Notifications are now active for this wallet.",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        await message.answer(
            f"❌ No wallets added. All {skipped} address(es) already exist.",
            reply_markup=get_main_menu_keyboard()
        )


@router.message(EditWalletStates.waiting_for_assets)
async def process_assets_filter(message: Message, state: FSMContext):
    """Process asset filter input."""
    data = await state.get_data()
    wallet_id = data.get('wallet_id')
    
    if not wallet_id:
        await state.clear()
        await message.answer("❌ Error: wallet not found")
        return
    
    wallet = await db.get_wallet_by_id(wallet_id)
    if not wallet or wallet.user_id != message.from_user.id:
        await state.clear()
        await message.answer("❌ Error: wallet not found")
        return
    
    # Parse assets
    assets_text = message.text.strip().upper()
    if assets_text == "*" or assets_text.lower() == "all":
        wallet.filters.assets = None
    else:
        assets = [a.strip() for a in assets_text.replace(',', ' ').split() if a.strip()]
        wallet.filters.assets = assets if assets else None
    
    # Update database
    await db.update_wallet_filters(wallet_id, wallet.filters)
    
    await message.answer(
        f"✅ Asset filter updated!\n\n"
        f"Filtering: {', '.join(wallet.filters.assets) if wallet.filters.assets else 'All assets'}",
        reply_markup=get_back_to_menu_keyboard()
    )
    
    await state.clear()


@router.message(EditWalletStates.waiting_for_min_notional)
async def process_min_notional(message: Message, state: FSMContext):
    """Process minimum notional USD input."""
    data = await state.get_data()
    wallet_id = data.get('wallet_id')
    
    if not wallet_id:
        await state.clear()
        await message.answer("❌ Error: wallet not found")
        return
    
    wallet = await db.get_wallet_by_id(wallet_id)
    if not wallet or wallet.user_id != message.from_user.id:
        await state.clear()
        await message.answer("❌ Error: wallet not found")
        return
    
    # Parse amount
    try:
        amount = float(message.text.strip().replace('$', '').replace(',', ''))
        if amount < 0:
            raise ValueError("Amount must be positive")
        
        wallet.filters.min_notional_usd = amount
        await db.update_wallet_filters(wallet_id, wallet.filters)
        
        await message.answer(
            f"✅ Minimum notional updated to ${amount:,.2f}",
            reply_markup=get_back_to_menu_keyboard()
        )
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a valid number.")
    
    await state.clear()


@router.message(EditLiquidationStates.waiting_for_pairs)
async def process_liq_pairs(message: Message, state: FSMContext):
    """Process liquidation pairs filter."""
    settings = await db.get_user_settings(message.from_user.id)
    
    pairs_text = message.text.strip().upper()
    if pairs_text == "*" or pairs_text.lower() == "all":
        settings.liquidation_filters.pairs = None
    else:
        pairs = [p.strip() for p in pairs_text.replace(',', ' ').split() if p.strip()]
        settings.liquidation_filters.pairs = pairs if pairs else None
    
    await db.update_liquidation_settings(message.from_user.id, settings.liquidation_filters)
    
    await message.answer(
        f"✅ Liquidation pairs filter updated!\n\n"
        f"Filtering: {', '.join(settings.liquidation_filters.pairs) if settings.liquidation_filters.pairs else 'All pairs'}",
        reply_markup=get_back_to_menu_keyboard()
    )
    
    await state.clear()


@router.message(EditLiquidationStates.waiting_for_min_notional)
async def process_liq_min_notional(message: Message, state: FSMContext):
    """Process liquidation minimum notional."""
    settings = await db.get_user_settings(message.from_user.id)
    
    try:
        amount = float(message.text.strip().replace('$', '').replace(',', ''))
        if amount < 0:
            raise ValueError("Amount must be positive")
        
        settings.liquidation_filters.min_notional_usd = amount
        await db.update_liquidation_settings(message.from_user.id, settings.liquidation_filters)
        
        await message.answer(
            f"✅ Liquidation minimum notional updated to ${amount:,.2f}",
            reply_markup=get_back_to_menu_keyboard()
        )
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a valid number.")
    
    await state.clear()


@router.message(EditGlobalFilterStates.waiting_for_assets)
async def process_global_assets_filter(message: Message, state: FSMContext):
    """Process global asset filter input."""
    settings = await db.get_user_settings(message.from_user.id)

    if not settings.global_wallet_filters:
        await state.clear()
        await message.answer("❌ Error: global filters not found", reply_markup=get_main_menu_keyboard())
        return

    # Parse assets
    assets_text = message.text.strip().upper()
    if assets_text == "*" or assets_text.lower() == "all":
        settings.global_wallet_filters.assets = None
    else:
        assets = [a.strip() for a in assets_text.replace(',', ' ').split() if a.strip()]
        settings.global_wallet_filters.assets = assets if assets else None

    # Update database
    await db.update_global_wallet_filters(message.from_user.id, settings.global_wallet_filters)

    await message.answer(
        f"✅ Global asset filter updated!\n\n"
        f"Filtering: {', '.join(settings.global_wallet_filters.assets) if settings.global_wallet_filters.assets else 'All assets'}",
        reply_markup=get_back_to_menu_keyboard()
    )

    await state.clear()


@router.message(EditGlobalFilterStates.waiting_for_min_notional)
async def process_global_min_notional(message: Message, state: FSMContext):
    """Process global minimum notional USD input."""
    settings = await db.get_user_settings(message.from_user.id)

    if not settings.global_wallet_filters:
        await state.clear()
        await message.answer("❌ Error: global filters not found", reply_markup=get_main_menu_keyboard())
        return

    # Parse amount
    try:
        amount = float(message.text.strip().replace('$', '').replace(',', ''))
        if amount < 0:
            raise ValueError("Amount must be positive")

        settings.global_wallet_filters.min_notional_usd = amount
        await db.update_global_wallet_filters(message.from_user.id, settings.global_wallet_filters)

        await message.answer(
            f"✅ Global minimum notional updated to ${amount:,.2f}",
            reply_markup=get_back_to_menu_keyboard()
        )
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a valid number.")

    await state.clear()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    """Cancel current operation."""
    await state.clear()
    await message.answer("❌ Operation cancelled.", reply_markup=get_main_menu_keyboard())
