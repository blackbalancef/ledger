"""User service for managing user-related operations."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.users import User


class UserService:
    """Service for user operations."""

    @staticmethod
    async def get_or_create_user(
        telegram_id: int,
        username: Optional[str],
        session: AsyncSession,
    ) -> User:
        """
        Get existing user or create a new one.

        Args:
            telegram_id: Telegram user ID
            username: Telegram username
            session: Database session

        Returns:
            User object
        """
        # Try to find existing user
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Update username if changed
            if user.username != username:
                user.username = username
                await session.commit()
                logger.info(f"Updated username for user {telegram_id}")
            return user

        # Create new user
        user = User(
            telegram_id=telegram_id,
            username=username,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info(f"Created new user: {telegram_id} ({username})")
        
        # Copy default categories to new user
        from bot.services.category_service import CategoryService
        await CategoryService.copy_default_categories_to_user(user, session)
        logger.info(f"Copied default categories for new user {telegram_id}")

        return user

    @staticmethod
    async def update_default_currency(
        user: User,
        currency: str,
        session: AsyncSession,
    ) -> User:
        """
        Update user's default currency.

        Args:
            user: User object
            currency: New default currency code
            session: Database session

        Returns:
            Updated user object
        """
        user.default_currency = currency
        await session.commit()
        await session.refresh(user)
        logger.info(f"Updated default currency for user {user.telegram_id} to {currency}")
        return user

    @staticmethod
    async def update_preferred_report_currency(
        user: User,
        currency: str,
        session: AsyncSession,
    ) -> User:
        """
        Update user's preferred report display currency.

        Args:
            user: User object
            currency: New preferred report currency code
            session: Database session

        Returns:
            Updated user object
        """
        user.preferred_report_currency = currency
        await session.commit()
        await session.refresh(user)
        logger.info(f"Updated preferred report currency for user {user.telegram_id} to {currency}")
        return user

    @staticmethod
    async def get_recent_currencies(
        user: User,
        session: AsyncSession,
        limit: int = 3,
    ) -> list[str]:
        """
        Get user's recently used currencies.

        Args:
            user: User object
            session: Database session
            limit: Maximum number of currencies to return

        Returns:
            List of currency codes
        """
        from models.transactions import Transaction
        from sqlalchemy import func

        # Get distinct currencies ordered by max(created_at) for each currency
        stmt = (
            select(Transaction.currency)
            .where(Transaction.user_id == user.id)
            .group_by(Transaction.currency)
            .order_by(func.max(Transaction.created_at).desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        currencies = [row[0] for row in result.fetchall()]

        return currencies

    @staticmethod
    async def get_user_by_telegram_id(
        telegram_id: int,
        session: AsyncSession,
    ) -> Optional[User]:
        """
        Get user by Telegram ID.

        Args:
            telegram_id: Telegram user ID
            session: Database session

        Returns:
            User or None if not found
        """
        stmt = select(User).where(User.telegram_id == telegram_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_username(
        username: str,
        session: AsyncSession,
    ) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Telegram username (without @)
            session: Database session

        Returns:
            User or None if not found
        """
        stmt = select(User).where(User.username == username)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

