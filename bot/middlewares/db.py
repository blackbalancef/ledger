"""Database session middleware for aiogram."""

from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from core.db import async_session_maker


class DbSessionMiddleware(BaseMiddleware):
    """Middleware to inject database session into handlers."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Execute handler with database session.

        Args:
            handler: Handler function
            event: Telegram event
            data: Handler data

        Returns:
            Handler result
        """
        async with async_session_maker() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except Exception as e:
                await session.rollback()
                logger.error(f"Error in handler: {e}")
                raise

