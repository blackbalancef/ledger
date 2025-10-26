"""Debt service for managing debt operations."""

from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional
from uuid import UUID

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from loguru import logger

from models.debts import Debt
from models.transactions import Transaction, TransactionTypeEnum
from models.users import User
from core.fx_rates import fx_service


class DebtService:
    """Service for debt operations."""

    @staticmethod
    async def create_debt(
        creditor: User,
        debtor: User,
        amount: float,
        currency: str,
        category_id: Optional[int],
        note: Optional[str],
        related_transaction_id: Optional[UUID],
        session: AsyncSession,
    ) -> Debt:
        """
        Create a new debt between two users.

        Args:
            creditor: User who is owed money (paid the bill)
            debtor: User who owes money
            amount: Amount debtor owes
            currency: Currency code
            category_id: Optional category ID
            note: Optional note
            related_transaction_id: Link to the transaction that created this debt
            session: Database session

        Returns:
            Created debt
        """
        # Get FX rates
        rates = await fx_service.get_rates_for_transaction(currency, session)

        # Convert amount to minor units (cents)
        amount_minor = Debt.to_minor_units(amount, currency)

        # Calculate converted amounts
        amount_decimal = Decimal(str(amount))
        amount_eur = amount_decimal * rates["eur"]
        amount_usd = amount_decimal * rates["usd"]

        # Create debt
        debt = Debt(
            creditor_user_id=creditor.id,
            debtor_user_id=debtor.id,
            amount_minor=amount_minor,
            currency=currency,
            amount_eur=amount_eur,
            amount_usd=amount_usd,
            fx_rate_to_eur=rates["eur"],
            fx_rate_to_usd=rates["usd"],
            category_id=category_id,
            note=note,
            related_transaction_id=related_transaction_id,
            is_settled=False,
            created_at=datetime.utcnow(),
        )

        session.add(debt)
        await session.commit()
        await session.refresh(debt)

        logger.info(
            f"Created debt: {debt.id}, creditor={creditor.telegram_id}, "
            f"debtor={debtor.telegram_id}, amount={amount} {currency}"
        )

        return debt

    @staticmethod
    async def get_user_debts(
        user: User,
        session: AsyncSession,
        only_unsettled: bool = True,
    ) -> List[Debt]:
        """
        Get all debts for a user (both owed and owing).

        Args:
            user: User object
            session: Database session
            only_unsettled: Only return unsettled debts

        Returns:
            List of debts
        """
        stmt = (
            select(Debt)
            .options(
                joinedload(Debt.creditor),
                joinedload(Debt.debtor),
                joinedload(Debt.category),
            )
            .where(
                or_(
                    Debt.creditor_user_id == user.id,
                    Debt.debtor_user_id == user.id,
                )
            )
        )

        if only_unsettled:
            stmt = stmt.where(Debt.is_settled == False)

        stmt = stmt.order_by(Debt.created_at.desc())

        result = await session.execute(stmt)
        debts = result.scalars().unique().all()

        return list(debts)

    @staticmethod
    async def settle_debt(
        debt_id: UUID,
        user: User,
        session: AsyncSession,
    ) -> Transaction:
        """
        Settle a debt by creating a SETTLEMENT transaction.

        Args:
            debt_id: Debt ID to settle
            user: User object (must be the debtor or creditor)
            session: Database session

        Returns:
            Settlement transaction

        Raises:
            ValueError: If debt not found or user is not involved
        """
        # Get debt
        stmt = select(Debt).where(Debt.id == debt_id)
        result = await session.execute(stmt)
        debt = result.scalar_one_or_none()

        if not debt:
            raise ValueError("Debt not found")

        # Check if user is involved
        if debt.creditor_user_id != user.id and debt.debtor_user_id != user.id:
            raise ValueError("You are not involved in this debt")

        # Check if already settled
        if debt.is_settled:
            raise ValueError("Debt is already settled")

        # Import here to avoid circular dependency
        from bot.services.transaction_service import TransactionService
        
        # Determine transaction direction
        # If debtor is settling, they pay (negative amount for them)
        # If creditor is settling, they receive (positive amount)
        is_debtor = debt.debtor_user_id == user.id

        if is_debtor:
            # Debtor pays - this is an expense for debtor
            transaction_type = TransactionTypeEnum.EXPENSE
            settlement_user = user
        else:
            # Creditor receives - this is income for creditor
            transaction_type = TransactionTypeEnum.INCOME
            settlement_user = user

        # Create settlement transaction
        settlement = await TransactionService.create_transaction(
            user=settlement_user,
            amount=float(debt.amount),
            currency=debt.currency,
            transaction_type=transaction_type,
            category_id=debt.category_id,
            note=f"Settlement of debt {debt_id}",
            session=session,
        )

        # Update debt as settled
        debt.is_settled = True
        await session.commit()

        logger.info(f"Settled debt {debt_id} with transaction {settlement.id}")

        return settlement

    @staticmethod
    async def get_debt_summary(
        user: User,
        session: AsyncSession,
        display_currency: Optional[str] = None,
    ) -> Dict:
        """
        Get debt summary for a user, grouped by currency and user.

        Args:
            user: User object
            session: Database session
            display_currency: Currency to display summary in (default: user's preferred_report_currency)

        Returns:
            Dictionary with debt summary
        """
        if display_currency is None:
            display_currency = user.preferred_report_currency

        # Get all unsettled debts
        debts = await DebtService.get_user_debts(user, session, only_unsettled=True)

        # Group debts
        owed_to_me = {}  # {user: {currency: amount}}
        i_owe = {}  # {user: {currency: amount}}

        for debt in debts:
            if debt.creditor_user_id == user.id:
                # Someone owes me
                debtor_name = debt.debtor.username or f"User {debt.debtor.telegram_id}"
                if debtor_name not in owed_to_me:
                    owed_to_me[debtor_name] = {}
                owed_to_me[debtor_name][debt.currency] = (
                    owed_to_me[debtor_name].get(debt.currency, 0) + float(debt.amount)
                )
            else:
                # I owe someone
                creditor_name = debt.creditor.username or f"User {debt.creditor.telegram_id}"
                if creditor_name not in i_owe:
                    i_owe[creditor_name] = {}
                i_owe[creditor_name][debt.currency] = (
                    i_owe[creditor_name].get(debt.currency, 0) + float(debt.amount)
                )

        return {
            "display_currency": display_currency,
            "owed_to_me": owed_to_me,
            "i_owe": i_owe,
        }

    @staticmethod
    async def get_debt_by_id(
        debt_id: UUID,
        user: User,
        session: AsyncSession,
    ) -> Optional[Debt]:
        """
        Get debt by ID, ensuring user is involved.

        Args:
            debt_id: Debt ID
            user: User object
            session: Database session

        Returns:
            Debt or None if not found
        """
        stmt = (
            select(Debt)
            .options(
                joinedload(Debt.creditor),
                joinedload(Debt.debtor),
                joinedload(Debt.category),
            )
            .where(
                Debt.id == debt_id,
                or_(
                    Debt.creditor_user_id == user.id,
                    Debt.debtor_user_id == user.id,
                ),
            )
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

