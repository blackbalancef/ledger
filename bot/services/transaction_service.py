"""Transaction service for managing transaction operations."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, List, Dict
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from loguru import logger

from models.transactions import Transaction, TransactionTypeEnum
from models.categories import Category, TransactionType
from models.users import User
from core.fx_rates import fx_service


class TransactionService:
    """Service for transaction operations."""

    @staticmethod
    async def create_transaction(
        user: User,
        amount: float,
        currency: str,
        transaction_type: TransactionTypeEnum,
        category_id: Optional[int],
        note: Optional[str],
        session: AsyncSession,
        at_time: Optional[datetime] = None,
    ) -> Transaction:
        """
        Create a new transaction with currency conversion.

        Args:
            user: User object
            amount: Amount in major currency units
            currency: Currency code
            transaction_type: Type of transaction
            category_id: Category ID
            note: Optional note
            session: Database session
            at_time: Optional transaction timestamp (defaults to current time)

        Returns:
            Created transaction
        """
        # Use provided at_time or default to current time
        transaction_time = at_time if at_time is not None else datetime.utcnow()
        
        # Get FX rates for the transaction date
        transaction_date = transaction_time.date() if isinstance(transaction_time, datetime) else transaction_time
        rates = await fx_service.get_rates_for_transaction(currency, session, target_date=transaction_date)

        # Convert amount to minor units (cents)
        amount_minor = Transaction.to_minor_units(amount, currency)

        # Calculate converted amounts
        amount_decimal = Decimal(str(amount))
        amount_eur = amount_decimal * rates["eur"]
        amount_usd = amount_decimal * rates["usd"]

        # Create transaction
        transaction = Transaction(
            user_id=user.id,
            transaction_type=transaction_type,
            amount_minor=amount_minor,
            currency=currency,
            amount_eur=amount_eur,
            amount_usd=amount_usd,
            fx_rate_to_eur=rates["eur"],
            fx_rate_to_usd=rates["usd"],
            category_id=category_id,
            note=note,
            at_time=transaction_time,
        )

        session.add(transaction)
        await session.commit()
        await session.refresh(transaction)

        logger.info(
            f"Created transaction: {transaction.id} for user {user.telegram_id}, "
            f"{amount} {currency} ({transaction_type.value})"
        )

        return transaction

    @staticmethod
    async def reverse_transaction(
        transaction_id: UUID,
        user: User,
        session: AsyncSession,
    ) -> Transaction:
        """
        Create a reversal transaction for a given transaction.

        Args:
            transaction_id: Original transaction ID
            user: User object
            session: Database session

        Returns:
            Reversal transaction

        Raises:
            ValueError: If transaction not found or doesn't belong to user
        """
        # Get original transaction
        stmt = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.user_id == user.id,
        )
        result = await session.execute(stmt)
        original = result.scalar_one_or_none()

        if not original:
            raise ValueError("Transaction not found or access denied")

        # Create reversal
        reversal = Transaction(
            user_id=user.id,
            transaction_type=TransactionTypeEnum.REVERSAL,
            amount_minor=original.amount_minor,
            currency=original.currency,
            amount_eur=original.amount_eur,
            amount_usd=original.amount_usd,
            fx_rate_to_eur=original.fx_rate_to_eur,
            fx_rate_to_usd=original.fx_rate_to_usd,
            category_id=original.category_id,
            note=f"Reversal of transaction {transaction_id}",
            at_time=datetime.utcnow(),
        )

        session.add(reversal)
        await session.commit()
        await session.refresh(reversal)

        logger.info(f"Created reversal {reversal.id} for transaction {transaction_id}")

        return reversal

    @staticmethod
    async def get_user_history(
        user: User,
        session: AsyncSession,
        limit: int = 10,
    ) -> List[Transaction]:
        """
        Get user's transaction history.

        Args:
            user: User object
            session: Database session
            limit: Maximum number of transactions

        Returns:
            List of transactions
        """
        stmt = (
            select(Transaction)
            .options(joinedload(Transaction.category))
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.at_time.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        transactions = result.scalars().all()

        return list(transactions)

    @staticmethod
    async def get_monthly_report(
        user: User,
        session: AsyncSession,
        year: Optional[int] = None,
        month: Optional[int] = None,
        display_currency: Optional[str] = None,
    ) -> Dict:
        """
        Get monthly report for user.

        Args:
            user: User object
            session: Database session
            year: Year (default: current)
            month: Month (default: current)
            display_currency: Currency to display report in (default: user's preferred_report_currency)

        Returns:
            Report dictionary with expenses, income, and totals in display_currency
        """
        now = datetime.utcnow()
        year = year or now.year
        month = month or now.month
        
        # Use user's preferred report currency if not specified
        if display_currency is None:
            display_currency = user.preferred_report_currency

        # Calculate date range
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        # Determine which amount field to aggregate based on display currency
        # Use stored amounts directly for USD/EUR to avoid conversion errors
        if display_currency.upper() == "USD":
            amount_field = Transaction.amount_usd
            base_currency = "USD"
        elif display_currency.upper() == "EUR":
            amount_field = Transaction.amount_eur
            base_currency = "EUR"
        else:
            # For other currencies, aggregate EUR and convert
            amount_field = Transaction.amount_eur
            base_currency = "EUR"

        # Query expenses by category
        expenses_stmt = (
            select(
                Category.name,
                Category.icon,
                func.sum(amount_field).label("total_amount"),
            )
            .join(Transaction.category)
            .where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.transaction_type == TransactionTypeEnum.EXPENSE,
                    Transaction.at_time >= start_date,
                    Transaction.at_time < end_date,
                )
            )
            .group_by(Category.name, Category.icon)
            .order_by(Category.name)
        )
        expenses_result = await session.execute(expenses_stmt)
        expenses = expenses_result.fetchall()

        # Query income by category
        income_stmt = (
            select(
                Category.name,
                Category.icon,
                func.sum(amount_field).label("total_amount"),
            )
            .join(Transaction.category)
            .where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.transaction_type == TransactionTypeEnum.INCOME,
                    Transaction.at_time >= start_date,
                    Transaction.at_time < end_date,
                )
            )
            .group_by(Category.name, Category.icon)
            .order_by(Category.name)
        )
        income_result = await session.execute(income_stmt)
        income = income_result.fetchall()

        # Calculate totals
        total_expenses = sum(e.total_amount for e in expenses)
        total_income = sum(i.total_amount for i in income)
        balance = total_income - total_expenses

        # Get conversion rate from base currency to display_currency (if needed)
        if display_currency.upper() == base_currency:
            conversion_rate = Decimal("1.0")
        else:
            conversion_rate = await fx_service.get_rate(base_currency, display_currency, session)

        # Convert all amounts to display_currency
        expenses_list = [
            {
                "category": e.name,
                "icon": e.icon,
                "amount": e.total_amount * conversion_rate,
            }
            for e in expenses
        ]

        income_list = [
            {
                "category": i.name,
                "icon": i.icon,
                "amount": i.total_amount * conversion_rate,
            }
            for i in income
        ]

        return {
            "period": {"year": year, "month": month},
            "display_currency": display_currency,
            "expenses": expenses_list,
            "income": income_list,
            "totals": {
                "expenses": total_expenses * conversion_rate,
                "income": total_income * conversion_rate,
                "balance": balance * conversion_rate,
            },
        }

    @staticmethod
    async def get_date_range_report(
        user: User,
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        display_currency: Optional[str] = None,
    ) -> Dict:
        """
        Get report for a custom date range.

        Args:
            user: User object
            session: Database session
            start_date: Start date (inclusive)
            end_date: End date (inclusive, will be set to end of day)
            display_currency: Currency to display report in (default: user's preferred_report_currency)

        Returns:
            Report dictionary with expenses, income, and totals in display_currency
        """
        # Use user's preferred report currency if not specified
        if display_currency is None:
            display_currency = user.preferred_report_currency

        # Ensure end_date is end of day
        if end_date.hour == 0 and end_date.minute == 0 and end_date.second == 0:
            end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)

        # Determine which amount field to aggregate based on display currency
        # Use stored amounts directly for USD/EUR to avoid conversion errors
        if display_currency.upper() == "USD":
            amount_field = Transaction.amount_usd
            base_currency = "USD"
        elif display_currency.upper() == "EUR":
            amount_field = Transaction.amount_eur
            base_currency = "EUR"
        else:
            # For other currencies, aggregate EUR and convert
            amount_field = Transaction.amount_eur
            base_currency = "EUR"

        # Query expenses by category
        expenses_stmt = (
            select(
                Category.name,
                Category.icon,
                func.sum(amount_field).label("total_amount"),
            )
            .join(Transaction.category)
            .where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.transaction_type == TransactionTypeEnum.EXPENSE,
                    Transaction.at_time >= start_date,
                    Transaction.at_time <= end_date,
                )
            )
            .group_by(Category.name, Category.icon)
            .order_by(Category.name)
        )
        expenses_result = await session.execute(expenses_stmt)
        expenses = expenses_result.fetchall()

        # Query income by category
        income_stmt = (
            select(
                Category.name,
                Category.icon,
                func.sum(amount_field).label("total_amount"),
            )
            .join(Transaction.category)
            .where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.transaction_type == TransactionTypeEnum.INCOME,
                    Transaction.at_time >= start_date,
                    Transaction.at_time <= end_date,
                )
            )
            .group_by(Category.name, Category.icon)
            .order_by(Category.name)
        )
        income_result = await session.execute(income_stmt)
        income = income_result.fetchall()

        # Calculate totals
        total_expenses = sum(e.total_amount for e in expenses)
        total_income = sum(i.total_amount for i in income)
        balance = total_income - total_expenses

        # Get conversion rate from base currency to display_currency (if needed)
        if display_currency.upper() == base_currency:
            conversion_rate = Decimal("1.0")
        else:
            conversion_rate = await fx_service.get_rate(base_currency, display_currency, session)

        # Convert all amounts to display_currency
        expenses_list = [
            {
                "category": e.name,
                "icon": e.icon,
                "amount": e.total_amount * conversion_rate,
            }
            for e in expenses
        ]

        income_list = [
            {
                "category": i.name,
                "icon": i.icon,
                "amount": i.total_amount * conversion_rate,
            }
            for i in income
        ]

        return {
            "date_range": {"start_date": start_date, "end_date": end_date},
            "display_currency": display_currency,
            "expenses": expenses_list,
            "income": income_list,
            "totals": {
                "expenses": total_expenses * conversion_rate,
                "income": total_income * conversion_rate,
                "balance": balance * conversion_rate,
            },
        }

    @staticmethod
    async def get_categories(
        transaction_type: str,
        user: User,
        session: AsyncSession,
    ) -> List[Category]:
        """
        Get categories by transaction type for a specific user.

        Args:
            transaction_type: Type of transaction ('EXPENSE' or 'INCOME' string)
            user: User object to filter categories
            session: Database session

        Returns:
            List of categories
        """
        # Convert string to TransactionType enum
        try:
            trans_type_enum = TransactionType(transaction_type)
        except ValueError:
            logger.error(f"Invalid transaction type: {transaction_type}")
            return []
        
        stmt = (
            select(Category)
            .where(
                Category.transaction_type == trans_type_enum,
                Category.user_id == user.id,
                Category.is_archived == False
            )
            .order_by(Category.is_default.desc(), Category.name)
        )
        result = await session.execute(stmt)
        categories = result.scalars().all()

        logger.info(f"Found {len(categories)} categories for type {transaction_type} and user {user.id}")

        return list(categories)

