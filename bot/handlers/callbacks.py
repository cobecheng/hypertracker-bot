"""
Callback query handlers for inline keyboard interactions.
"""
import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext

from bot.keyboards import (
    get_main_menu_keyboard, get_wallet_list_keyboard, get_wallet_detail_keyboard,
    get_wallet_edit_keyboard, get_notification_types_keyboard, get_order_type_keyboard,
    get_direction_keyboard, get_confirm_remove_keyboard, get_liquidation_settings_keyboard,
    get_venues_keyboard, get_back_to_menu_keyboard, get_global_settings_keyboard,
    get_global_filter_edit_keyboard, get_global_notification_types_keyboard,
    get_global_order_type_keyboard, get_global_direction_keyboard, get_evm_tracking_keyboard
)
from bot.handlers.commands import (
    AddWalletStates, EditWalletStates, EditLiquidationStates, EditGlobalFilterStates, db
)
from core.models import NotificationType, OrderType, Direction
from utils.filters import format_address

logger = logging.getLogger(__name__)

router = Router()

# Global reference to liquidation statistics (set by main.py)
liq_stats = None


@router.callback_query(F.data == "main_menu")
async def callback_main_menu(callback: CallbackQuery, state: FSMContext):
    """Show main menu."""
    await state.clear()

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

    await callback.message.edit_text(
        welcome_text,
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "add_wallet")
async def callback_add_wallet(callback: CallbackQuery, state: FSMContext):
    """Start add wallet flow."""
    await callback.message.edit_text(
        "➕ **Add Wallet**\n\n"
        "Send me one or more Hyperliquid wallet addresses.\n"
        "You can send multiple addresses separated by commas or newlines.\n\n"
        "Example:\n"
        "`0x1234567890abcdef...`\n"
        "or\n"
        "`0x1234..., 0x5678...`\n\n"
        "Type /cancel to abort.",
        parse_mode="Markdown"
    )
    
    await state.set_state(AddWalletStates.waiting_for_addresses)
    await callback.answer()


@router.callback_query(F.data == "my_wallets")
async def callback_my_wallets(callback: CallbackQuery):
    """Show user's wallets."""
    wallets = await db.get_user_wallets(callback.from_user.id)

    if not wallets:
        await callback.message.edit_text(
            "📋 **My Wallets**\n\n"
            "You don't have any wallets yet.\n"
            "Click 'Add Wallet' to start tracking!",
            reply_markup=get_main_menu_keyboard()
        )
    else:
        # Count active wallets
        active_count = sum(1 for w in wallets if w.active)

        await callback.message.edit_text(
            f"📋 **Tracked Wallets**\n\n"
            f"You have **{len(wallets)} wallet(s)** in your tracking list.\n"
            f"• Active: {active_count}\n"
            f"• Inactive: {len(wallets) - active_count}\n\n"
            f"Select a wallet to view details and edit settings:",
            reply_markup=get_wallet_list_keyboard(wallets)
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("wallet:"))
async def callback_wallet_detail(callback: CallbackQuery):
    """Show wallet details."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    # Format wallet info
    status = "✅ Active" if wallet.active else "❌ Inactive"
    notifications = "🔔 Enabled" if wallet.filters.notifications_enabled else "🔕 Disabled"

    # Replace underscores with spaces for notification types to avoid Markdown conflicts
    notify_types = ", ".join([nt.value.replace("_", " ").title() for nt in wallet.filters.notify_on]) if wallet.filters.notify_on else "None"
    assets = ", ".join(wallet.filters.assets) if wallet.filters.assets else "All"

    info_text = f"""
🔍 <b>Wallet Details</b>

<b>Name:</b> {wallet.alias if wallet.alias else 'No alias'}
<b>Address:</b> <code>{wallet.address}</code>
<b>Status:</b> {status}
<b>Notifications:</b> {notifications}

<b>Filters:</b>
• Types: {notify_types}
• Assets: {assets}
• Order Type: {wallet.filters.order_type.value.title()}
• Direction: {wallet.filters.direction.value.title()}
• Min Notional: ${wallet.filters.min_notional_usd:,.2f}
"""

    await callback.message.edit_text(
        info_text,
        reply_markup=get_wallet_detail_keyboard(wallet_id),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_wallet:"))
async def callback_edit_wallet(callback: CallbackQuery):
    """Show wallet edit menu."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"✏️ **Edit Wallet Filters**\n\n"
        f"Wallet: {wallet.alias if wallet.alias else format_address(wallet.address)}\n\n"
        f"Choose what to edit:",
        reply_markup=get_wallet_edit_keyboard(wallet_id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_wallet:"))
async def callback_toggle_wallet(callback: CallbackQuery):
    """Toggle wallet notifications on/off."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    # Toggle notifications
    wallet.filters.notifications_enabled = not wallet.filters.notifications_enabled
    await db.update_wallet_filters(wallet_id, wallet.filters)
    
    status = "enabled" if wallet.filters.notifications_enabled else "disabled"
    await callback.answer(f"✅ Notifications {status}", show_alert=True)
    
    # Refresh wallet detail view
    await callback_wallet_detail(callback)


@router.callback_query(F.data.startswith("edit_notify_types:"))
async def callback_edit_notify_types(callback: CallbackQuery):
    """Edit notification types."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 **Select Notification Types**\n\n"
        "Choose which events should trigger notifications:",
        reply_markup=get_notification_types_keyboard(wallet_id, wallet.filters.notify_on)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_notif:"))
async def callback_toggle_notif(callback: CallbackQuery):
    """Toggle specific notification type."""
    parts = callback.data.split(":")
    wallet_id = int(parts[1])
    notif_type = NotificationType(parts[2])
    
    wallet = await db.get_wallet_by_id(wallet_id)
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    # Toggle notification type
    if notif_type in wallet.filters.notify_on:
        wallet.filters.notify_on.remove(notif_type)
    else:
        wallet.filters.notify_on.append(notif_type)
    
    await db.update_wallet_filters(wallet_id, wallet.filters)
    
    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_notification_types_keyboard(wallet_id, wallet.filters.notify_on)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("edit_assets:"))
async def callback_edit_assets(callback: CallbackQuery, state: FSMContext):
    """Start editing asset filter."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    current = ", ".join(wallet.filters.assets) if wallet.filters.assets else "All assets"
    
    await callback.message.edit_text(
        f"🪙 **Filter by Asset**\n\n"
        f"Current: {current}\n\n"
        f"Send asset symbols separated by spaces or commas.\n"
        f"Examples: `BTC ETH SOL` or `BTC, ETH, SOL`\n\n"
        f"Send `*` or `all` for all assets.\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )
    
    await state.update_data(wallet_id=wallet_id)
    await state.set_state(EditWalletStates.waiting_for_assets)
    await callback.answer()


@router.callback_query(F.data.startswith("edit_order_type:"))
async def callback_edit_order_type(callback: CallbackQuery):
    """Edit order type filter."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📊 **Order Type Filter**\n\n"
        "Select which order types to track:",
        reply_markup=get_order_type_keyboard(wallet_id, wallet.filters.order_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_order_type:"))
async def callback_set_order_type(callback: CallbackQuery):
    """Set order type."""
    parts = callback.data.split(":")
    wallet_id = int(parts[1])
    order_type = OrderType(parts[2])
    
    wallet = await db.get_wallet_by_id(wallet_id)
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    wallet.filters.order_type = order_type
    await db.update_wallet_filters(wallet_id, wallet.filters)
    
    await callback.answer(f"✅ Order type set to {order_type.value.title()}", show_alert=True)
    
    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_order_type_keyboard(wallet_id, wallet.filters.order_type)
    )


@router.callback_query(F.data.startswith("edit_direction:"))
async def callback_edit_direction(callback: CallbackQuery):
    """Edit direction filter."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📈 **Direction Filter**\n\n"
        "Select which trade directions to track:",
        reply_markup=get_direction_keyboard(wallet_id, wallet.filters.direction)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_direction:"))
async def callback_set_direction(callback: CallbackQuery):
    """Set direction filter."""
    parts = callback.data.split(":")
    wallet_id = int(parts[1])
    direction = Direction(parts[2])
    
    wallet = await db.get_wallet_by_id(wallet_id)
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    wallet.filters.direction = direction
    await db.update_wallet_filters(wallet_id, wallet.filters)
    
    await callback.answer(f"✅ Direction set to {direction.value.title()}", show_alert=True)
    
    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_direction_keyboard(wallet_id, wallet.filters.direction)
    )


@router.callback_query(F.data.startswith("edit_min_notional:"))
async def callback_edit_min_notional(callback: CallbackQuery, state: FSMContext):
    """Start editing minimum notional."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"💰 **Minimum Notional USD**\n\n"
        f"Current: ${wallet.filters.min_notional_usd:,.2f}\n\n"
        f"Send the new minimum notional value in USD.\n"
        f"Example: `1000` or `$1,000`\n\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )
    
    await state.update_data(wallet_id=wallet_id)
    await state.set_state(EditWalletStates.waiting_for_min_notional)
    await callback.answer()


@router.callback_query(F.data.startswith("remove_wallet:"))
async def callback_remove_wallet(callback: CallbackQuery):
    """Confirm wallet removal."""
    wallet_id = int(callback.data.split(":")[1])
    wallet = await db.get_wallet_by_id(wallet_id)
    
    if not wallet or wallet.user_id != callback.from_user.id:
        await callback.answer("❌ Wallet not found", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"🗑️ **Remove Wallet**\n\n"
        f"Are you sure you want to remove this wallet?\n\n"
        f"**{wallet.alias if wallet.alias else format_address(wallet.address)}**\n"
        f"`{wallet.address}`\n\n"
        f"This action cannot be undone.",
        reply_markup=get_confirm_remove_keyboard(wallet_id),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_remove:"))
async def callback_confirm_remove(callback: CallbackQuery):
    """Actually remove the wallet."""
    wallet_id = int(callback.data.split(":")[1])
    
    success = await db.delete_wallet(wallet_id, callback.from_user.id)
    
    if success:
        await callback.answer("✅ Wallet removed", show_alert=True)
        await callback_my_wallets(callback)
    else:
        await callback.answer("❌ Failed to remove wallet", show_alert=True)


@router.callback_query(F.data == "liquidations")
async def callback_liquidations(callback: CallbackQuery):
    """Show liquidation settings."""
    settings = await db.get_user_settings(callback.from_user.id)
    liq_filters = settings.liquidation_filters
    
    status = "🔔 Enabled" if liq_filters.enabled else "🔕 Disabled"
    venues = ", ".join(liq_filters.venues) if liq_filters.venues else "None"
    pairs = ", ".join(liq_filters.pairs) if liq_filters.pairs else "All"
    
    text = f"""
🚨 **Liquidation Monitor**

**Status:** {status}
**Venues:** {venues}
**Pairs:** {pairs}
**Min Notional:** ${liq_filters.min_notional_usd:,.2f}

Configure your liquidation alert settings below:
"""
    
    await callback.message.edit_text(
        text,
        reply_markup=get_liquidation_settings_keyboard(liq_filters.enabled)
    )
    await callback.answer()


@router.callback_query(F.data == "toggle_liq_monitor")
async def callback_toggle_liq_monitor(callback: CallbackQuery):
    """Toggle liquidation monitoring."""
    settings = await db.get_user_settings(callback.from_user.id)
    settings.liquidation_filters.enabled = not settings.liquidation_filters.enabled

    await db.update_liquidation_settings(callback.from_user.id, settings.liquidation_filters)

    status = "enabled" if settings.liquidation_filters.enabled else "disabled"
    await callback.answer(f"✅ Liquidation alerts {status}", show_alert=True)

    # Refresh view
    await callback_liquidations(callback)


@router.callback_query(F.data == "liq_stats")
async def callback_liq_stats(callback: CallbackQuery):
    """Show liquidation statistics for the last hour."""
    from datetime import datetime, timedelta

    if liq_stats is None:
        await callback.answer("❌ Statistics not available", show_alert=True)
        return

    # Build statistics message
    message_lines = ["📊 **Liquidation Statistics (Last Hour)**\n"]

    total_received = 0
    total_sent = 0

    for venue in ['Binance', 'Bybit', 'Gate.io']:
        if venue in liq_stats:
            stats = liq_stats[venue]

            # Calculate time since last reset
            time_since_reset = datetime.now() - stats['last_reset']
            minutes_ago = int(time_since_reset.total_seconds() / 60)

            total = stats['total']
            sent = stats['sent']
            filtered = total - sent

            total_received += total
            total_sent += sent

            # Format percentage
            sent_pct = (sent / total * 100) if total > 0 else 0

            message_lines.append(
                f"\n**{venue}**\n"
                f"├ Total received: {total:,}\n"
                f"├ Sent to you: {sent:,} ({sent_pct:.1f}%)\n"
                f"└ Filtered out: {filtered:,}\n"
            )

    # Add summary
    total_filtered = total_received - total_sent
    message_lines.append(
        f"\n**Summary**\n"
        f"├ Total across all venues: {total_received:,}\n"
        f"├ Notifications sent: {total_sent:,}\n"
        f"└ Filtered out: {total_filtered:,}\n"
    )

    # Add note about hourly reset
    message_lines.append(
        f"\n_Stats reset hourly per venue_\n"
        f"_Filtered = below your min notional or wrong venue/pair_"
    )

    await callback.message.edit_text(
        "\n".join(message_lines),
        reply_markup=get_liquidation_settings_keyboard(
            (await db.get_user_settings(callback.from_user.id)).liquidation_filters.enabled
        )
    )
    await callback.answer()


@router.callback_query(F.data == "edit_liq_venues")
async def callback_edit_liq_venues(callback: CallbackQuery):
    """Edit liquidation venues."""
    settings = await db.get_user_settings(callback.from_user.id)
    
    await callback.message.edit_text(
        "🏢 **Select Venues**\n\n"
        "Choose which venues to monitor for liquidations:",
        reply_markup=get_venues_keyboard(settings.liquidation_filters.venues)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_venue:"))
async def callback_toggle_venue(callback: CallbackQuery):
    """Toggle venue selection."""
    venue = callback.data.split(":", 1)[1]
    settings = await db.get_user_settings(callback.from_user.id)
    
    if venue in settings.liquidation_filters.venues:
        settings.liquidation_filters.venues.remove(venue)
    else:
        settings.liquidation_filters.venues.append(venue)
    
    await db.update_liquidation_settings(callback.from_user.id, settings.liquidation_filters)
    
    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_venues_keyboard(settings.liquidation_filters.venues)
    )
    await callback.answer()


@router.callback_query(F.data == "edit_liq_pairs")
async def callback_edit_liq_pairs(callback: CallbackQuery, state: FSMContext):
    """Start editing liquidation pairs."""
    settings = await db.get_user_settings(callback.from_user.id)
    current = ", ".join(settings.liquidation_filters.pairs) if settings.liquidation_filters.pairs else "All pairs"
    
    await callback.message.edit_text(
        f"🪙 **Filter Liquidation Pairs**\n\n"
        f"Current: {current}\n\n"
        f"Send pair symbols separated by spaces or commas.\n"
        f"Examples: `BTC ETH SOL` or `BTC-USDT, ETH-USDT`\n\n"
        f"Send `*` or `all` for all pairs.\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )
    
    await state.set_state(EditLiquidationStates.waiting_for_pairs)
    await callback.answer()


@router.callback_query(F.data == "edit_liq_min_notional")
async def callback_edit_liq_min_notional(callback: CallbackQuery, state: FSMContext):
    """Start editing liquidation minimum notional."""
    settings = await db.get_user_settings(callback.from_user.id)
    
    await callback.message.edit_text(
        f"💰 **Liquidation Min Notional**\n\n"
        f"Current: ${settings.liquidation_filters.min_notional_usd:,.2f}\n\n"
        f"Send the new minimum notional value in USD.\n"
        f"Example: `50000` or `$50,000`\n\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )
    
    await state.set_state(EditLiquidationStates.waiting_for_min_notional)
    await callback.answer()


@router.callback_query(F.data == "stats")
async def callback_stats(callback: CallbackQuery):
    """Show bot stats."""
    from bot.handlers.commands import start_time
    import time
    from datetime import datetime

    stats = await db.get_stats()
    uptime_seconds = time.time() - start_time

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

    await callback.message.edit_text(stats_text, reply_markup=get_back_to_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "global_settings")
async def callback_global_settings(callback: CallbackQuery):
    """Show global filter settings."""
    settings = await db.get_user_settings(callback.from_user.id)

    if settings.global_wallet_filters:
        filters = settings.global_wallet_filters

        # Format notification types - replace underscores with spaces
        notify_types = ", ".join([t.value.replace("_", " ").title() for t in filters.notify_on]) if filters.notify_on else "None"

        # Format assets
        assets = ", ".join(filters.assets) if filters.assets else "All"

        text = f"""
⚙️ <b>Global Wallet Filter Settings</b>

These filters apply to all wallets by default. Individual wallet filters will override these settings.

<b>Status:</b> {"🔔 Enabled" if filters.notifications_enabled else "🔕 Disabled"}
<b>Notify On:</b> {notify_types}
<b>Assets:</b> {assets}
<b>Order Type:</b> {filters.order_type.value}
<b>Direction:</b> {filters.direction.value}
<b>Min Notional:</b> ${filters.min_notional_usd:,.2f}

Choose an option below:
"""
    else:
        text = """
⚙️ <b>Global Wallet Filter Settings</b>

You haven't set global filters yet. Global filters apply to all wallets by default, unless a wallet has individual filters configured.

Setting global filters can help you:
• Avoid setting the same filters for each wallet
• Quickly enable/disable all notifications
• Filter by specific notification types, assets, or trade sizes

Choose an option below:
"""

    await callback.message.edit_text(
        text,
        reply_markup=get_global_settings_keyboard(settings.global_wallet_filters is not None),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "set_global_filters")
async def callback_set_global_filters(callback: CallbackQuery):
    """Set default global filters."""
    from core.models import WalletFilters

    settings = await db.get_user_settings(callback.from_user.id)

    # Create default filters if they don't exist
    if not settings.global_wallet_filters:
        settings.global_wallet_filters = WalletFilters()
        await db.update_global_wallet_filters(callback.from_user.id, settings.global_wallet_filters)

    await callback.answer("✅ Global filters initialized with defaults", show_alert=True)

    # Refresh the global settings view
    await callback_global_settings(callback)


@router.callback_query(F.data == "edit_global_filters")
async def callback_edit_global_filters(callback: CallbackQuery):
    """Show menu to edit global filters."""
    await callback.message.edit_text(
        "✏️ **Edit Global Filters**\n\n"
        "Choose what to edit:",
        reply_markup=get_global_filter_edit_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "remove_global_filters")
async def callback_remove_global_filters(callback: CallbackQuery):
    """Remove global filters."""
    settings = await db.get_user_settings(callback.from_user.id)
    settings.global_wallet_filters = None
    await db.update_user_settings(callback.from_user.id, settings)

    await callback.answer("✅ Global filters removed", show_alert=True)

    # Refresh the global settings view
    await callback_global_settings(callback)


@router.callback_query(F.data == "edit_global_notify_types")
async def callback_edit_global_notify_types(callback: CallbackQuery):
    """Edit global notification types."""
    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Please set global filters first", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 **Select Global Notification Types**\n\n"
        "Choose which events should trigger notifications by default:",
        reply_markup=get_global_notification_types_keyboard(settings.global_wallet_filters.notify_on)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_global_notif:"))
async def callback_toggle_global_notif(callback: CallbackQuery):
    """Toggle global notification type."""
    notif_type = NotificationType(callback.data.split(":", 1)[1])

    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Global filters not found", show_alert=True)
        return

    # Toggle notification type
    if notif_type in settings.global_wallet_filters.notify_on:
        settings.global_wallet_filters.notify_on.remove(notif_type)
    else:
        settings.global_wallet_filters.notify_on.append(notif_type)

    await db.update_global_wallet_filters(callback.from_user.id, settings.global_wallet_filters)

    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_global_notification_types_keyboard(settings.global_wallet_filters.notify_on)
    )
    await callback.answer()


@router.callback_query(F.data == "edit_global_assets")
async def callback_edit_global_assets(callback: CallbackQuery, state: FSMContext):
    """Start editing global asset filter."""
    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Please set global filters first", show_alert=True)
        return

    current = ", ".join(settings.global_wallet_filters.assets) if settings.global_wallet_filters.assets else "All assets"

    await callback.message.edit_text(
        f"🪙 **Filter by Asset (Global)**\n\n"
        f"Current: {current}\n\n"
        f"Send asset symbols separated by spaces or commas.\n"
        f"Examples: `BTC ETH SOL` or `BTC, ETH, SOL`\n\n"
        f"Send `*` or `all` for all assets.\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )

    await state.set_state(EditGlobalFilterStates.waiting_for_assets)
    await callback.answer()


@router.callback_query(F.data == "edit_global_order_type")
async def callback_edit_global_order_type(callback: CallbackQuery):
    """Edit global order type filter."""
    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Please set global filters first", show_alert=True)
        return

    await callback.message.edit_text(
        "📊 **Global Order Type Filter**\n\n"
        "Select which order types to track by default:",
        reply_markup=get_global_order_type_keyboard(settings.global_wallet_filters.order_type)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_global_order_type:"))
async def callback_set_global_order_type(callback: CallbackQuery):
    """Set global order type."""
    order_type = OrderType(callback.data.split(":", 1)[1])

    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Global filters not found", show_alert=True)
        return

    settings.global_wallet_filters.order_type = order_type
    await db.update_global_wallet_filters(callback.from_user.id, settings.global_wallet_filters)

    await callback.answer(f"✅ Order type set to {order_type.value.title()}", show_alert=True)

    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_global_order_type_keyboard(settings.global_wallet_filters.order_type)
    )


@router.callback_query(F.data == "edit_global_direction")
async def callback_edit_global_direction(callback: CallbackQuery):
    """Edit global direction filter."""
    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Please set global filters first", show_alert=True)
        return

    await callback.message.edit_text(
        "📈 **Global Direction Filter**\n\n"
        "Select which trade directions to track by default:",
        reply_markup=get_global_direction_keyboard(settings.global_wallet_filters.direction)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("set_global_direction:"))
async def callback_set_global_direction(callback: CallbackQuery):
    """Set global direction filter."""
    direction = Direction(callback.data.split(":", 1)[1])

    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Global filters not found", show_alert=True)
        return

    settings.global_wallet_filters.direction = direction
    await db.update_global_wallet_filters(callback.from_user.id, settings.global_wallet_filters)

    await callback.answer(f"✅ Direction set to {direction.value.title()}", show_alert=True)

    # Refresh keyboard
    await callback.message.edit_reply_markup(
        reply_markup=get_global_direction_keyboard(settings.global_wallet_filters.direction)
    )


@router.callback_query(F.data == "edit_global_min_notional")
async def callback_edit_global_min_notional(callback: CallbackQuery, state: FSMContext):
    """Start editing global minimum notional."""
    settings = await db.get_user_settings(callback.from_user.id)

    if not settings.global_wallet_filters:
        await callback.answer("❌ Please set global filters first", show_alert=True)
        return

    await callback.message.edit_text(
        f"💰 **Global Minimum Notional USD**\n\n"
        f"Current: ${settings.global_wallet_filters.min_notional_usd:,.2f}\n\n"
        f"Send the new minimum notional value in USD.\n"
        f"Example: `1000` or `$1,000`\n\n"
        f"Type /cancel to abort.",
        parse_mode="Markdown"
    )

    await state.set_state(EditGlobalFilterStates.waiting_for_min_notional)
    await callback.answer()


@router.callback_query(F.data == "evm_tracking")
async def callback_evm_tracking(callback: CallbackQuery):
    """Show EVM tracking submenu."""
    addresses = await db.get_user_evm_addresses(callback.from_user.id)

    active_count = sum(1 for addr in addresses if addr.active)

    text = f"""
🔷 **EVM Transaction Tracking**

Track token transfers, treasury movements, and deployer activities on EVM chains.

**Status:**
• Tracked addresses: {len(addresses)}
• Active: {active_count}

Choose an option below:
"""

    await callback.message.edit_text(
        text,
        reply_markup=get_evm_tracking_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "evm_add_address")
async def callback_evm_add_address(callback: CallbackQuery, state: FSMContext):
    """Start add EVM address flow."""
    from bot.handlers.evm_commands import AddEVMAddressStates

    await callback.message.edit_text(
        "📝 **Add EVM Address**\n\n"
        "Send the Ethereum address you want to track:\n\n"
        "Example: `0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb`\n\n"
        "This can be:\n"
        "• Token contract address\n"
        "• Wallet address (EOA)\n"
        "• Treasury/deployer address\n\n"
        "Type /cancel to abort.",
        parse_mode="Markdown"
    )
    await state.set_state(AddEVMAddressStates.waiting_for_address)
    await callback.answer()


@router.callback_query(F.data == "evm_list")
async def callback_evm_list(callback: CallbackQuery):
    """List all EVM addresses tracked by the user."""
    user_id = callback.from_user.id

    addresses = await db.get_user_evm_addresses(user_id)

    if not addresses:
        await callback.message.edit_text(
            "📋 **Tracked EVM Addresses**\n\n"
            "You're not tracking any EVM addresses yet.\n\n"
            "Click 'Add EVM Address' to start tracking!",
            reply_markup=get_evm_tracking_keyboard()
        )
        await callback.answer()
        return

    # Group by token
    tokens = {}
    for addr in addresses:
        token = addr.token_symbol or "Custom"
        if token not in tokens:
            tokens[token] = []
        tokens[token].append(addr)

    # Build message
    lines = ["📋 **Your Tracked EVM Addresses**\n"]

    for token, addr_list in tokens.items():
        lines.append(f"\n🪙 {token}:")
        for addr in addr_list:
            status = "🟢" if addr.active else "🔴"
            address_short = f"{addr.address[:10]}...{addr.address[-8:]}"
            lines.append(f"  {status} {addr.label}")
            lines.append(f"     `{address_short}`")

    lines.append(f"\n\nTotal: {len(addresses)} address(es)")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=get_evm_tracking_keyboard(),
        parse_mode="Markdown"
    )
    await callback.answer()


@router.callback_query(F.data == "evm_stop_tracking")
async def callback_evm_stop_tracking(callback: CallbackQuery):
    """Show buttons to stop tracking specific addresses."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    user_id = callback.from_user.id

    addresses = await db.get_user_evm_addresses(user_id)

    if not addresses:
        await callback.message.edit_text(
            "❌ **No Tracked Addresses**\n\n"
            "You're not tracking any EVM addresses.",
            reply_markup=get_evm_tracking_keyboard()
        )
        await callback.answer()
        return

    # Create inline keyboard with buttons for each address
    keyboard = []
    for addr in addresses:
        if addr.active:
            address_short = f"{addr.address[:6]}...{addr.address[-4:]}"
            button_text = f"❌ {addr.label} ({address_short})"
            callback_data = f"stop_evm:{addr.id}"
            keyboard.append([InlineKeyboardButton(text=button_text, callback_data=callback_data)])

    if not keyboard:
        await callback.message.edit_text(
            "ℹ️ **All Inactive**\n\n"
            "All your tracked addresses are already inactive.",
            reply_markup=get_evm_tracking_keyboard()
        )
        await callback.answer()
        return

    # Add back button
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="evm_tracking")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(
        "❌ **Stop Tracking**\n\n"
        "Select an address to stop tracking:",
        reply_markup=markup
    )
    await callback.answer()


@router.callback_query(F.data.startswith("stop_evm:"))
async def callback_stop_evm_confirm(callback: CallbackQuery):
    """Handle stop tracking callback."""
    address_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Delete the address
    success = await db.delete_evm_address(address_id, user_id)

    if success:
        await callback.answer("✅ Stopped tracking", show_alert=True)
        # Refresh the EVM tracking menu
        await callback_evm_tracking(callback)
    else:
        await callback.answer("❌ Error stopping tracking", show_alert=True)
