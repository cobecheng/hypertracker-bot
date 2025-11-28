"""
Notification system for sending formatted messages to users.
Handles message formatting and delivery with rate limiting.
"""
import asyncio
import logging
from typing import Dict, Set

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError

from core.models import (
    HyperliquidFill, HyperliquidDeposit, HyperliquidWithdrawal,
    LiquidationEvent, Wallet
)
from utils.formatting import (
    format_fill_notification, format_deposit_notification,
    format_withdrawal_notification, format_liquidation_notification
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
    
    async def notify_fill(self, user_id: int, fill: HyperliquidFill, wallet: Wallet):
        """Send fill notification to user."""
        if user_id in self._blocked_users:
            return
        
        try:
            message = format_fill_notification(fill, wallet)
            await self._send_message(user_id, message)
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
            await self._send_message(user_id, message)
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
            await self._send_message(user_id, message)
        except Exception as e:
            logger.error(f"Error sending withdrawal notification to {user_id}: {e}")
    
    async def notify_liquidation(self, user_id: int, liquidation: LiquidationEvent):
        """Send liquidation notification to user."""
        if user_id in self._blocked_users:
            return
        
        try:
            message = format_liquidation_notification(liquidation)
            await self._send_message(user_id, message)
        except Exception as e:
            logger.error(f"Error sending liquidation notification to {user_id}: {e}")
    
    async def _send_message(self, user_id: int, text: str):
        """
        Send message with rate limiting and error handling.
        
        Args:
            user_id: Telegram user ID
            text: Message text to send
        """
        # Rate limiting
        await asyncio.sleep(self._rate_limit_delay)
        
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=None,  # Plain text for better emoji support
                disable_web_page_preview=True
            )
        
        except TelegramRetryAfter as e:
            # Telegram rate limit hit
            logger.warning(f"Rate limit hit for user {user_id}, waiting {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
            # Retry once
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode=None,
                disable_web_page_preview=True
            )
        
        except TelegramForbiddenError:
            # User blocked the bot
            logger.warning(f"User {user_id} blocked the bot")
            self._blocked_users.add(user_id)
        
        except Exception as e:
            logger.error(f"Error sending message to {user_id}: {e}")
            raise
