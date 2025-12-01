"""
Notification system for sending formatted messages to users.
Handles message formatting and delivery with rate limiting.
"""
import asyncio
import logging
from typing import Dict, Set, Optional, Tuple

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

from config import get_settings
from core.models import (
    HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal,
    HyperliquidTwapOrder, LiquidationEvent, Wallet
)
from utils.formatting import (
    format_fill_notification, format_deposit_notification,
    format_withdrawal_notification, format_liquidation_notification,
    format_twap_notification
)

logger = logging.getLogger(__name__)


class Notifier:
    """
    Handles sending notifications to Telegram users.
    Manages rate limiting and error handling.
    """

    def __init__(self, bot: Bot):
        """Initialize notifier with bot instance."""
        self.bot = bot
        self._rate_limit_delay = 0.05  # 50ms between messages
        self._last_send_time: Dict[int, float] = {}
        self._blocked_users: Set[int] = set()
        self._settings = get_settings()

    def _parse_chat_destination(self, chat_config: Optional[str]) -> Tuple[Optional[int], Optional[int]]:
        """
        Parse chat destination from config string.

        Args:
            chat_config: Either "chat_id" or "chat_id:thread_id"

        Returns:
            Tuple of (chat_id, message_thread_id)
        """
        if not chat_config:
            return None, None

        try:
            if ':' in chat_config:
                chat_id_str, thread_id_str = chat_config.split(':', 1)
                return int(chat_id_str), int(thread_id_str)
            else:
                return int(chat_config), None
        except ValueError:
            logger.error(f"Invalid chat destination format: {chat_config}")
            return None, None

    def _get_destination(self, user_id: int, notification_type: str) -> Tuple[int, Optional[int]]:
        """
        Get the destination chat_id and thread_id for a notification.

        Args:
            user_id: User ID to send to if no override configured
            notification_type: Either 'trades' or 'liquidations'

        Returns:
            Tuple of (chat_id, message_thread_id)
        """
        # Check if user is whitelisted for group notifications
        is_whitelisted = (
            self._settings.whitelisted_user_id is None or  # No whitelist = all users
            user_id == self._settings.whitelisted_user_id   # User is whitelisted
        )

        # Only use group chat if user is whitelisted
        if is_whitelisted:
            if notification_type == 'trades':
                chat_id, thread_id = self._parse_chat_destination(self._settings.trades_chat_id)
            elif notification_type == 'liquidations':
                chat_id, thread_id = self._parse_chat_destination(self._settings.liquidations_chat_id)
            else:
                chat_id, thread_id = None, None

            # Fall back to user's private chat if no override configured
            if chat_id is None:
                chat_id = user_id

            return chat_id, thread_id
        else:
            # Non-whitelisted users always get private chat notifications
            return user_id, None
    
    async def notify_fill(self, user_id: int, fill: HyperliquidFill, wallet: Wallet):
        """Send fill notification to user."""
        if user_id in self._blocked_users:
            return

        try:
            message = format_fill_notification(fill, wallet)
            chat_id, thread_id = self._get_destination(user_id, 'trades')
            await self._send_message(chat_id, message, thread_id)
        except Exception as e:
            logger.error(f"Error sending fill notification to {user_id}: {e}")

    async def notify_deposit(self, user_id: int, deposit: HyperliquidDeposit, wallet: Wallet):
        """Send deposit notification to user."""
        if user_id in self._blocked_users:
            return

        try:
            message = format_deposit_notification(
                wallet, deposit.usd, deposit.time, deposit.hash
            )
            chat_id, thread_id = self._get_destination(user_id, 'trades')
            await self._send_message(chat_id, message, thread_id)
        except Exception as e:
            logger.error(f"Error sending deposit notification to {user_id}: {e}")

    async def notify_withdrawal(self, user_id: int, withdrawal: HyperliquidWithdrawal, wallet: Wallet):
        """Send withdrawal notification to user."""
        if user_id in self._blocked_users:
            return

        try:
            message = format_withdrawal_notification(
                wallet, withdrawal.usd, withdrawal.time, withdrawal.hash
            )
            chat_id, thread_id = self._get_destination(user_id, 'trades')
            await self._send_message(chat_id, message, thread_id)
        except Exception as e:
            logger.error(f"Error sending withdrawal notification to {user_id}: {e}")

    async def notify_liquidation(self, user_id: int, liquidation: LiquidationEvent):
        """Send liquidation notification to user."""
        if user_id in self._blocked_users:
            return

        try:
            message = format_liquidation_notification(liquidation)
            chat_id, thread_id = self._get_destination(user_id, 'liquidations')
            await self._send_message(chat_id, message, thread_id)
        except Exception as e:
            logger.error(f"Error sending liquidation notification to {user_id}: {e}")

    async def notify_twap(self, user_id: int, twap: HyperliquidTwapOrder, wallet: Wallet):
        """Send TWAP order notification to user."""
        if user_id in self._blocked_users:
            return

        try:
            message = format_twap_notification(twap, wallet)
            chat_id, thread_id = self._get_destination(user_id, 'trades')
            await self._send_message(chat_id, message, thread_id)
        except Exception as e:
            logger.error(f"Error sending TWAP notification to {user_id}: {e}")
    
    async def _send_message(self, chat_id: int, text: str, message_thread_id: Optional[int] = None):
        """
        Send message with rate limiting and error handling.

        Args:
            chat_id: Telegram chat ID (user, group, or supergroup)
            text: Message text to send
            message_thread_id: Optional topic/thread ID for supergroups
        """
        # Rate limiting
        await asyncio.sleep(self._rate_limit_delay)

        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=message_thread_id,
                parse_mode=None,  # Plain text for better emoji support
                disable_web_page_preview=True
            )

        except TelegramRetryAfter as e:
            # Telegram rate limit hit
            logger.warning(f"Rate limit hit for chat {chat_id}, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            # Retry once
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                message_thread_id=message_thread_id,
                parse_mode=None,
                disable_web_page_preview=True
            )

        except TelegramForbiddenError:
            # User blocked the bot or bot removed from group
            logger.warning(f"Bot blocked or removed from chat {chat_id}")
            self._blocked_users.add(chat_id)

        except Exception as e:
            logger.error(f"Error sending message to chat {chat_id}: {e}")
            raise
