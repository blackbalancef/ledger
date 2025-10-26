"""Category service for managing user-specific categories."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from models.categories import Category, TransactionType
from models.users import User
from models.transactions import Transaction


class CategoryService:
    """Service for category operations."""

    @staticmethod
    async def get_user_categories(
        user: User,
        session: AsyncSession,
        transaction_type: Optional[str] = None,
        include_archived: bool = False,
    ) -> List[Category]:
        """
        Get user's categories, optionally filtered by transaction type.

        Args:
            user: User object
            session: Database session
            transaction_type: Optional filter by 'EXPENSE' or 'INCOME'
            include_archived: Whether to include archived categories

        Returns:
            List of user's categories
        """
        stmt = select(Category).where(Category.user_id == user.id)
        
        if transaction_type:
            try:
                trans_type_enum = TransactionType(transaction_type)
                stmt = stmt.where(Category.transaction_type == trans_type_enum)
            except ValueError:
                logger.error(f"Invalid transaction type: {transaction_type}")
        
        if not include_archived:
            stmt = stmt.where(Category.is_archived == False)
        
        stmt = stmt.order_by(Category.is_default.desc(), Category.name)
        
        result = await session.execute(stmt)
        categories = result.scalars().all()
        
        logger.info(f"Found {len(categories)} categories for user {user.id}")
        return list(categories)

    @staticmethod
    async def create_category(
        user: User,
        name: str,
        icon: str,
        transaction_type: str,
        session: AsyncSession,
        description: Optional[str] = None,
    ) -> Category:
        """
        Create a new category for user.

        Args:
            user: User object
            name: Category name
            icon: Category icon (emoji)
            transaction_type: 'EXPENSE' or 'INCOME'
            description: Optional description
            session: Database session

        Returns:
            Created category
        """
        try:
            trans_type_enum = TransactionType(transaction_type)
        except ValueError:
            raise ValueError(f"Invalid transaction type: {transaction_type}")
        
        category = Category(
            name=name,
            icon=icon,
            transaction_type=trans_type_enum,
            description=description,
            user_id=user.id,
            is_default=False,
            is_archived=False,
        )
        
        session.add(category)
        await session.commit()
        await session.refresh(category)
        
        logger.info(f"Created category {category.id} ({name}) for user {user.id}")
        return category

    @staticmethod
    async def update_category(
        category_id: int,
        user: User,
        session: AsyncSession,
        name: Optional[str] = None,
        icon: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Category:
        """
        Update category fields.

        Args:
            category_id: Category ID to update
            user: User object (for authorization)
            name: New name (optional)
            icon: New icon (optional)
            description: New description (optional)
            session: Database session

        Returns:
            Updated category

        Raises:
            ValueError: If category not found or doesn't belong to user
        """
        stmt = select(Category).where(
            Category.id == category_id,
            Category.user_id == user.id,
        )
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        
        if not category:
            raise ValueError("Category not found or access denied")
        
        if name is not None:
            category.name = name
        if icon is not None:
            category.icon = icon
        if description is not None:
            category.description = description
        
        await session.commit()
        await session.refresh(category)
        
        logger.info(f"Updated category {category.id} for user {user.id}")
        return category

    @staticmethod
    async def archive_category(
        category_id: int,
        user: User,
        session: AsyncSession,
        migrate_to_category_id: Optional[int] = None,
    ) -> bool:
        """
        Archive a category and optionally migrate transactions to another category.

        Args:
            category_id: Category ID to archive
            user: User object (for authorization)
            migrate_to_category_id: Optional category to migrate transactions to
            session: Database session

        Returns:
            True if archived successfully

        Raises:
            ValueError: If category not found or doesn't belong to user
        """
        # Get category to archive
        stmt = select(Category).where(
            Category.id == category_id,
            Category.user_id == user.id,
        )
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        
        if not category:
            raise ValueError("Category not found or access denied")
        
        # If migration target specified, migrate transactions
        if migrate_to_category_id:
            # Verify target category belongs to user
            target_stmt = select(Category).where(
                Category.id == migrate_to_category_id,
                Category.user_id == user.id,
            )
            target_result = await session.execute(target_stmt)
            target_category = target_result.scalar_one_or_none()
            
            if not target_category:
                raise ValueError("Target category not found or access denied")
            
            # Update transactions
            update_stmt = (
                Transaction.__table__.update()
                .where(Transaction.category_id == category_id)
                .values(category_id=migrate_to_category_id)
            )
            await session.execute(update_stmt)
            
            logger.info(f"Migrated transactions from category {category_id} to {migrate_to_category_id}")
        
        # Archive the category
        category.is_archived = True
        await session.commit()
        
        logger.info(f"Archived category {category_id} for user {user.id}")
        return True

    @staticmethod
    async def unarchive_category(
        category_id: int,
        user: User,
        session: AsyncSession,
    ) -> Category:
        """
        Unarchive (restore) a category.

        Args:
            category_id: Category ID to unarchive
            user: User object (for authorization)
            session: Database session

        Returns:
            Unarchived category

        Raises:
            ValueError: If category not found or doesn't belong to user
        """
        stmt = select(Category).where(
            Category.id == category_id,
            Category.user_id == user.id,
        )
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        
        if not category:
            raise ValueError("Category not found or access denied")
        
        category.is_archived = False
        await session.commit()
        await session.refresh(category)
        
        logger.info(f"Unarchived category {category_id} for user {user.id}")
        return category

    @staticmethod
    async def copy_default_categories_to_user(
        user: User,
        session: AsyncSession,
    ) -> List[Category]:
        """
        Copy default template categories to a new user.

        Args:
            user: User object
            session: Database session

        Returns:
            List of copied categories
        """
        # Get default template categories (user_id IS NULL)
        stmt = select(Category).where(Category.user_id.is_(None))
        result = await session.execute(stmt)
        template_categories = result.scalars().all()
        
        if not template_categories:
            logger.warning("No template categories found")
            return []
        
        # Check if user already has categories
        existing_stmt = select(Category).where(Category.user_id == user.id).limit(1)
        existing_result = await session.execute(existing_stmt)
        has_categories = existing_result.scalar_one_or_none() is not None
        
        if has_categories:
            logger.info(f"User {user.id} already has categories, skipping copy")
            return []
        
        # Copy template categories to user
        copied_categories = []
        for template in template_categories:
            user_category = Category(
                name=template.name,
                icon=template.icon,
                transaction_type=template.transaction_type,
                description=None,  # Templates don't have descriptions initially
                user_id=user.id,
                is_default=template.is_default,
                is_archived=False,
            )
            session.add(user_category)
            copied_categories.append(user_category)
        
        await session.commit()
        
        # Refresh categories to get IDs
        for cat in copied_categories:
            await session.refresh(cat)
        
        logger.info(f"Copied {len(copied_categories)} default categories to user {user.id}")
        return copied_categories

    @staticmethod
    async def get_category_by_id(
        category_id: int,
        user: User,
        session: AsyncSession,
    ) -> Optional[Category]:
        """
        Get category by ID, ensuring it belongs to user.

        Args:
            category_id: Category ID
            user: User object
            session: Database session

        Returns:
            Category or None if not found
        """
        stmt = select(Category).where(
            Category.id == category_id,
            Category.user_id == user.id,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

