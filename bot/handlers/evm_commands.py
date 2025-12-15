"""
Telegram command handlers for EVM contract tracking.
Allows users to track tokens, deployers, and treasury addresses.
"""
import logging
from typing import Optional

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from core.database import Database
from core.evm_models import TrackedAddress, AddressType

logger = logging.getLogger(__name__)

router = Router()

# Global reference (set by main.py)
db: Optional[Database] = None


class AddEVMAddressStates(StatesGroup):
    """FSM states for adding custom EVM address."""
    waiting_for_address = State()
    waiting_for_label = State()


@router.message(Command("track_lit"))
async def cmd_track_lit(message: Message):
    """
    Start tracking LIT token (Lighter).
    Adds all three addresses: token, treasury, deployer.
    """
    user_id = message.from_user.id

    # LIT token addresses
    addresses = [
        TrackedAddress(
            user_id=user_id,
            address="0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2",
            label="LIT Token Contract",
            address_type=AddressType.TOKEN_CONTRACT,
            token_contract="0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2",
            token_symbol="LIT",
            min_value_usd=0.0
        ),
        TrackedAddress(
            user_id=user_id,
            address="0x077842A5670CB4C83dca62bDA4c36592a5B31891",
            label="LIT Treasury (Safe Multisig)",
            address_type=AddressType.TREASURY,
            token_contract="0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2",
            token_symbol="LIT",
            min_value_usd=0.0
        ),
        TrackedAddress(
            user_id=user_id,
            address="0x004Fe354757574E2DEB35fDb304383366f313099",
            label="LIT Deployer",
            address_type=AddressType.DEPLOYER,
            token_contract="0x232CE3bd40fCd6f80f3d55A522d03f25Df784Ee2",
            token_symbol="LIT",
            min_value_usd=0.0
        ),
    ]

    # Add addresses to database
    added_count = 0
    skipped_count = 0

    for addr in addresses:
        result = await db.add_evm_address(addr)
        if result:
            added_count += 1
        else:
            skipped_count += 1

    # Build response message
    if added_count > 0:
        message_text = (
            f"✅ Now tracking LIT token activities!\n\n"
            f"Added {added_count} address(es):\n"
            f"{'🔐 Treasury (1B LIT)' if added_count >= 2 else ''}\n"
            f"{'👤 Deployer' if added_count >= 3 else ''}\n"
            f"{'📄 Token Contract' if added_count >= 1 else ''}\n\n"
            f"You'll receive alerts for:\n"
            f"• Treasury token movements 🔐\n"
            f"• Deployer activity 👤\n"
            f"• Large LIT transfers 📊\n\n"
            f"Notifications will be sent to your 'CA Tracking' channel.\n\n"
            f"Use /list_evm to see all tracked addresses."
        )
    else:
        message_text = (
            f"ℹ️ You're already tracking all LIT addresses!\n\n"
            f"Use /list_evm to see your tracked addresses."
        )

    await message.answer(message_text)


@router.message(Command("list_evm"))
async def cmd_list_evm(message: Message):
    """List all EVM addresses tracked by the user."""
    user_id = message.from_user.id

    addresses = await db.get_user_evm_addresses(user_id)

    if not addresses:
        await message.answer(
            "You're not tracking any EVM addresses yet.\n\n"
            "Use /track_lit to start tracking LIT token!\n"
            "Or use /add_evm_address to track custom addresses."
        )
        return

    # Group by token
    tokens = {}
    for addr in addresses:
        token = addr.token_symbol or "Custom"
        if token not in tokens:
            tokens[token] = []
        tokens[token].append(addr)

    # Build message
    lines = ["📋 Your tracked EVM addresses:\n"]

    for token, addr_list in tokens.items():
        lines.append(f"\n🪙 {token}:")
        for addr in addr_list:
            status = "🟢" if addr.active else "🔴"
            address_short = f"{addr.address[:10]}...{addr.address[-8:]}"
            lines.append(f"  {status} {addr.label}")
            lines.append(f"     {address_short}")

    lines.append(f"\n\nTotal: {len(addresses)} address(es)")
    lines.append("\nUse /stop_evm_tracking to stop tracking.")

    await message.answer("\n".join(lines))


@router.message(Command("add_evm_address"))
async def cmd_add_evm_address(message: Message, state: FSMContext):
    """Start the process of adding a custom EVM address to track."""
    await message.answer(
        "📝 Please send the Ethereum address you want to track:\n\n"
        "Example: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb\n\n"
        "This can be:\n"
        "• Token contract address\n"
        "• Wallet address (EOA)\n"
        "• Treasury/deployer address\n\n"
        "Send /cancel to cancel."
    )
    await state.set_state(AddEVMAddressStates.waiting_for_address)


@router.message(AddEVMAddressStates.waiting_for_address)
async def process_evm_address(message: Message, state: FSMContext):
    """Validate and store the EVM address."""
    address = message.text.strip()

    # Basic validation
    if not address.startswith("0x") or len(address) != 42:
        await message.answer(
            "❌ Invalid Ethereum address format.\n\n"
            "Address should start with 0x and be 42 characters long.\n"
            "Example: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb\n\n"
            "Please try again or send /cancel to cancel."
        )
        return

    # Checksum address (simple lowercase for now)
    checksummed_address = address.lower()

    # Store in FSM
    await state.update_data(address=checksummed_address)

    # Ask for label
    await message.answer(
        f"✅ Address validated: {checksummed_address[:10]}...{checksummed_address[-8:]}\n\n"
        f"Now, please provide a label for this address:\n\n"
        f"Example: My Token Treasury\n"
        f"Example: PEPE Deployer\n"
        f"Example: Whale Wallet #1"
    )
    await state.set_state(AddEVMAddressStates.waiting_for_label)


@router.message(AddEVMAddressStates.waiting_for_label)
async def process_evm_label(message: Message, state: FSMContext):
    """Store the label and create the tracked address."""
    label = message.text.strip()

    if len(label) < 3:
        await message.answer(
            "❌ Label must be at least 3 characters long.\n\n"
            "Please provide a descriptive label:"
        )
        return

    # Get stored address
    data = await state.get_data()
    address = data.get("address")

    # Create tracked address
    tracked_address = TrackedAddress(
        user_id=message.from_user.id,
        address=address,
        label=label,
        address_type=AddressType.CUSTOM,
        token_contract=None,
        token_symbol="CUSTOM",
        min_value_usd=0.0
    )

    # Add to database
    result = await db.add_evm_address(tracked_address)

    if result:
        await message.answer(
            f"✅ Successfully added!\n\n"
            f"Label: {label}\n"
            f"Address: {address[:10]}...{address[-8:]}\n\n"
            f"You'll now receive notifications for activity on this address.\n\n"
            f"Use /list_evm to see all your tracked addresses."
        )
    else:
        await message.answer(
            f"ℹ️ This address is already being tracked.\n\n"
            f"Use /list_evm to see your tracked addresses."
        )

    await state.clear()


@router.message(Command("stop_evm_tracking"))
async def cmd_stop_evm_tracking(message: Message):
    """Show buttons to stop tracking specific addresses."""
    user_id = message.from_user.id

    addresses = await db.get_user_evm_addresses(user_id)

    if not addresses:
        await message.answer("You're not tracking any EVM addresses.")
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
        await message.answer("All your tracked addresses are already inactive.")
        return

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await message.answer(
        "Select an address to stop tracking:",
        reply_markup=markup
    )


@router.callback_query(F.data.startswith("stop_evm:"))
async def callback_stop_evm(callback: CallbackQuery):
    """Handle stop tracking callback."""
    address_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Delete the address
    success = await db.delete_evm_address(address_id, user_id)

    if success:
        await callback.answer("✅ Stopped tracking", show_alert=True)
        await callback.message.edit_text("✅ Tracking stopped for this address.")
    else:
        await callback.answer("❌ Error stopping tracking", show_alert=True)


@router.message(Command("evm_help"))
async def cmd_evm_help(message: Message):
    """Show help for EVM tracking commands."""
    help_text = (
        "🔍 EVM Tracking Commands\n\n"
        "📊 Quick Start:\n"
        "/track_lit - Track LIT token (Lighter)\n\n"
        "📋 Management:\n"
        "/list_evm - List tracked addresses\n"
        "/add_evm_address - Track custom address\n"
        "/stop_evm_tracking - Stop tracking address\n\n"
        "💡 What you'll get:\n"
        "• Real-time token transfer alerts\n"
        "• Treasury/deployer activity\n"
        "• Large whale movements\n"
        "• CEX deposit/withdrawal signals\n\n"
        "🔔 Notifications are sent to your\n"
        "   'CA Tracking' channel (if configured)\n\n"
        "📚 Learn more: /help"
    )

    await message.answer(help_text)
