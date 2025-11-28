"""
Telegram inline keyboards for HyperTracker Bot.
Provides interactive menus and buttons for user interactions.
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.models import Wallet, NotificationType, OrderType, Direction


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Get the main menu keyboard."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="➕ Add Wallet", callback_data="add_wallet")
    )
    builder.row(
        InlineKeyboardButton(text="📋 My Wallets", callback_data="my_wallets")
    )
    builder.row(
        InlineKeyboardButton(text="⚙️ Global Settings", callback_data="global_settings")
    )
    builder.row(
        InlineKeyboardButton(text="🚨 Liquidation Monitor", callback_data="liquidations")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Stats", callback_data="stats")
    )

    return builder.as_markup()


def get_wallet_list_keyboard(wallets: list[Wallet]) -> InlineKeyboardMarkup:
    """Get keyboard showing list of user's wallets."""
    builder = InlineKeyboardBuilder()
    
    for wallet in wallets:
        display_name = wallet.alias if wallet.alias else wallet.address[:10] + "..."
        status = "✅" if wallet.active else "❌"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {display_name}",
                callback_data=f"wallet:{wallet.id}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="➕ Add Wallet", callback_data="add_wallet")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Menu", callback_data="main_menu")
    )
    
    return builder.as_markup()


def get_wallet_detail_keyboard(wallet_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for wallet detail view."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✏️ Edit Filters", callback_data=f"edit_wallet:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔔 Toggle Notifications", callback_data=f"toggle_wallet:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🗑️ Remove Wallet", callback_data=f"remove_wallet:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Wallets", callback_data="my_wallets")
    )
    
    return builder.as_markup()


def get_wallet_edit_keyboard(wallet_id: int) -> InlineKeyboardMarkup:
    """Get keyboard for editing wallet filters."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="📢 Notification Types", callback_data=f"edit_notify_types:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🪙 Filter by Asset", callback_data=f"edit_assets:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Order Type (Spot/Perp)", callback_data=f"edit_order_type:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="💰 Min Notional USD", callback_data=f"edit_min_notional:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="📈 Direction (Long/Short)", callback_data=f"edit_direction:{wallet_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Wallet", callback_data=f"wallet:{wallet_id}")
    )
    
    return builder.as_markup()


def get_notification_types_keyboard(wallet_id: int, current_types: list[NotificationType]) -> InlineKeyboardMarkup:
    """Get keyboard for selecting notification types."""
    builder = InlineKeyboardBuilder()
    
    all_types = [
        (NotificationType.OPEN, "Opens"),
        (NotificationType.CLOSE, "Closes"),
        (NotificationType.FILL, "Fills"),
        (NotificationType.LIQUIDATION, "Liquidations"),
        (NotificationType.DEPOSIT, "Deposits"),
        (NotificationType.WITHDRAWAL, "Withdrawals"),
    ]
    
    for notif_type, label in all_types:
        is_enabled = notif_type in current_types
        checkbox = "✅" if is_enabled else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{checkbox} {label}",
                callback_data=f"toggle_notif:{wallet_id}:{notif_type.value}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=f"edit_wallet:{wallet_id}")
    )
    
    return builder.as_markup()


def get_order_type_keyboard(wallet_id: int, current_type: OrderType) -> InlineKeyboardMarkup:
    """Get keyboard for selecting order type."""
    builder = InlineKeyboardBuilder()
    
    types = [
        (OrderType.BOTH, "Both"),
        (OrderType.SPOT, "Spot Only"),
        (OrderType.PERP, "Perp Only"),
    ]
    
    for order_type, label in types:
        is_selected = order_type == current_type
        marker = "✅" if is_selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {label}",
                callback_data=f"set_order_type:{wallet_id}:{order_type.value}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=f"edit_wallet:{wallet_id}")
    )
    
    return builder.as_markup()


def get_direction_keyboard(wallet_id: int, current_direction: Direction) -> InlineKeyboardMarkup:
    """Get keyboard for selecting trade direction."""
    builder = InlineKeyboardBuilder()
    
    directions = [
        (Direction.BOTH, "Both"),
        (Direction.LONG, "Long Only"),
        (Direction.SHORT, "Short Only"),
    ]
    
    for direction, label in directions:
        is_selected = direction == current_direction
        marker = "✅" if is_selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {label}",
                callback_data=f"set_direction:{wallet_id}:{direction.value}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data=f"edit_wallet:{wallet_id}")
    )
    
    return builder.as_markup()


def get_confirm_remove_keyboard(wallet_id: int) -> InlineKeyboardMarkup:
    """Get confirmation keyboard for removing wallet."""
    builder = InlineKeyboardBuilder()
    
    builder.row(
        InlineKeyboardButton(text="✅ Yes, Remove", callback_data=f"confirm_remove:{wallet_id}"),
        InlineKeyboardButton(text="❌ Cancel", callback_data=f"wallet:{wallet_id}")
    )
    
    return builder.as_markup()


def get_liquidation_settings_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    """Get keyboard for liquidation monitoring settings."""
    builder = InlineKeyboardBuilder()
    
    toggle_text = "🔕 Disable Alerts" if enabled else "🔔 Enable Alerts"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data="toggle_liq_monitor")
    )
    
    builder.row(
        InlineKeyboardButton(text="🏢 Select Venues", callback_data="edit_liq_venues")
    )
    builder.row(
        InlineKeyboardButton(text="🪙 Filter Pairs", callback_data="edit_liq_pairs")
    )
    builder.row(
        InlineKeyboardButton(text="💰 Min Notional USD", callback_data="edit_liq_min_notional")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Menu", callback_data="main_menu")
    )
    
    return builder.as_markup()


def get_venues_keyboard(selected_venues: list[str]) -> InlineKeyboardMarkup:
    """Get keyboard for selecting liquidation venues."""
    builder = InlineKeyboardBuilder()
    
    all_venues = ["Hyperliquid", "Lighter", "Binance", "Bybit", "OKX", "gTrade"]
    
    for venue in all_venues:
        is_selected = venue in selected_venues
        checkbox = "✅" if is_selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{checkbox} {venue}",
                callback_data=f"toggle_venue:{venue}"
            )
        )
    
    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data="liquidations")
    )
    
    return builder.as_markup()


def get_global_settings_keyboard(has_filters: bool) -> InlineKeyboardMarkup:
    """Get global settings keyboard."""
    builder = InlineKeyboardBuilder()

    if has_filters:
        builder.row(InlineKeyboardButton(text="✏️ Edit Global Filters", callback_data="edit_global_filters"))
        builder.row(InlineKeyboardButton(text="🗑️ Remove Global Filters", callback_data="remove_global_filters"))
    else:
        builder.row(InlineKeyboardButton(text="➕ Set Global Filters", callback_data="set_global_filters"))

    builder.row(InlineKeyboardButton(text="🔙 Back to Menu", callback_data="main_menu"))

    return builder.as_markup()


def get_global_filter_edit_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for editing global wallet filters."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="📢 Notification Types", callback_data="edit_global_notify_types")
    )
    builder.row(
        InlineKeyboardButton(text="🪙 Filter by Asset", callback_data="edit_global_assets")
    )
    builder.row(
        InlineKeyboardButton(text="📊 Order Type (Spot/Perp)", callback_data="edit_global_order_type")
    )
    builder.row(
        InlineKeyboardButton(text="💰 Min Notional USD", callback_data="edit_global_min_notional")
    )
    builder.row(
        InlineKeyboardButton(text="📈 Direction (Long/Short)", callback_data="edit_global_direction")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Global Settings", callback_data="global_settings")
    )

    return builder.as_markup()


def get_global_notification_types_keyboard(current_types: list[NotificationType]) -> InlineKeyboardMarkup:
    """Get keyboard for selecting global notification types."""
    builder = InlineKeyboardBuilder()

    all_types = [
        (NotificationType.OPEN, "Opens"),
        (NotificationType.CLOSE, "Closes"),
        (NotificationType.FILL, "Fills"),
        (NotificationType.LIQUIDATION, "Liquidations"),
        (NotificationType.DEPOSIT, "Deposits"),
        (NotificationType.WITHDRAWAL, "Withdrawals"),
    ]

    for notif_type, label in all_types:
        is_enabled = notif_type in current_types
        checkbox = "✅" if is_enabled else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{checkbox} {label}",
                callback_data=f"toggle_global_notif:{notif_type.value}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data="edit_global_filters")
    )

    return builder.as_markup()


def get_global_order_type_keyboard(current_type: OrderType) -> InlineKeyboardMarkup:
    """Get keyboard for selecting global order type."""
    builder = InlineKeyboardBuilder()

    types = [
        (OrderType.BOTH, "Both"),
        (OrderType.SPOT, "Spot Only"),
        (OrderType.PERP, "Perp Only"),
    ]

    for order_type, label in types:
        is_selected = order_type == current_type
        marker = "✅" if is_selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {label}",
                callback_data=f"set_global_order_type:{order_type.value}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data="edit_global_filters")
    )

    return builder.as_markup()


def get_global_direction_keyboard(current_direction: Direction) -> InlineKeyboardMarkup:
    """Get keyboard for selecting global trade direction."""
    builder = InlineKeyboardBuilder()

    directions = [
        (Direction.BOTH, "Both"),
        (Direction.LONG, "Long Only"),
        (Direction.SHORT, "Short Only"),
    ]

    for direction, label in directions:
        is_selected = direction == current_direction
        marker = "✅" if is_selected else "☐"
        builder.row(
            InlineKeyboardButton(
                text=f"{marker} {label}",
                callback_data=f"set_global_direction:{direction.value}"
            )
        )

    builder.row(
        InlineKeyboardButton(text="🔙 Back", callback_data="edit_global_filters")
    )

    return builder.as_markup()


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Get simple back to menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔙 Back to Menu", callback_data="main_menu")
    )
    return builder.as_markup()
