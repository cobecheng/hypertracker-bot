"""Authorization middleware for Telegram user interactions."""
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import Settings

logger = logging.getLogger(__name__)


class AuthorizedUserMiddleware(BaseMiddleware):
    """Allow only the configured Telegram user when a whitelist is set."""

    def __init__(self, settings: Settings):
        self.allowed_user_id = settings.whitelisted_user_id

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if self.allowed_user_id is None:
            return await handler(event, data)

        from_user = getattr(event, "from_user", None)
        if from_user and from_user.id == self.allowed_user_id:
            return await handler(event, data)

        user_id = from_user.id if from_user else None
        logger.warning("Rejected unauthorized Telegram user interaction from user_id=%s", user_id)

        message = "This bot is private."
        if isinstance(event, Message):
            await event.answer(message)
        elif isinstance(event, CallbackQuery):
            await event.answer(message, show_alert=True)
        return None
