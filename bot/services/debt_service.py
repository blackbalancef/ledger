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
        
        # Use SETTLEMENT type - debt settlements don't count as income/expense
        # because the net effect is zero (just recovering money already owed)
        settlement_user = user

        # Create settlement transaction
        settlement = await TransactionService.create_transaction(
            user=settlement_user,
            amount=float(debt.amount),
            currency=debt.currency,
            transaction_type=TransactionTypeEnum.SETTLEMENT,
            category_id=debt.category_id,
            note=f"Settlement of debt {debt_id}",
            session=session,
        )
        
        # Link settlement to debt and update debt as settled
        settlement.related_debt_id = debt_id
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

    @staticmethod
    async def calculate_net_debts(
        user1: User,
        user2: User,
        session: AsyncSession,
        base_currency: str = "EUR",
    ) -> Dict:
        """
        Calculate net debt between two users, converting all amounts to base currency.

        Args:
            user1: First user (from perspective of this user)
            user2: Second user
            session: Database session
            base_currency: Currency to use for calculation ("EUR" or "USD")

        Returns:
            Dictionary with:
            - net_amount: Net amount (positive if user1 owes user2, negative if user2 owes user1)
            - net_amount_decimal: Net amount as Decimal
            - debts_to_cancel: List of debts between the two users
            - breakdown: Detailed breakdown of calculation
        """
        # Get all unsettled debts between the two users
        stmt = (
            select(Debt)
            .options(
                joinedload(Debt.creditor),
                joinedload(Debt.debtor),
                joinedload(Debt.category),
            )
            .where(
                Debt.is_settled == False,
                or_(
                    and_(
                        Debt.creditor_user_id == user1.id,
                        Debt.debtor_user_id == user2.id,
                    ),
                    and_(
                        Debt.creditor_user_id == user2.id,
                        Debt.debtor_user_id == user1.id,
                    ),
                ),
            )
            .order_by(Debt.created_at)
        )
        result = await session.execute(stmt)
        debts = result.scalars().unique().all()

        if not debts:
            return {
                "net_amount": 0.0,
                "net_amount_decimal": Decimal("0"),
                "debts_to_cancel": [],
                "breakdown": [],
            }

        # Calculate net amount in base currency
        total_user1_owes = Decimal("0")  # user1 owes user2
        total_user2_owes = Decimal("0")  # user2 owes user1

        breakdown = []

        for debt in debts:
            # Get amount in base currency
            if base_currency == "EUR":
                amount_base = debt.amount_eur
            else:  # USD
                amount_base = debt.amount_usd

            if debt.creditor_user_id == user1.id and debt.debtor_user_id == user2.id:
                # user2 owes user1
                total_user2_owes += amount_base
                breakdown.append({
                    "debt": debt,
                    "direction": "user2_owes_user1",
                    "amount_base": amount_base,
                    "amount_original": float(debt.amount),
                    "currency": debt.currency,
                })
            elif debt.creditor_user_id == user2.id and debt.debtor_user_id == user1.id:
                # user1 owes user2
                total_user1_owes += amount_base
                breakdown.append({
                    "debt": debt,
                    "direction": "user1_owes_user2",
                    "amount_base": amount_base,
                    "amount_original": float(debt.amount),
                    "currency": debt.currency,
                })

        # Net: positive means user1 owes user2, negative means user2 owes user1
        net_amount_decimal = total_user1_owes - total_user2_owes
        net_amount = float(net_amount_decimal)

        return {
            "net_amount": net_amount,
            "net_amount_decimal": net_amount_decimal,
            "debts_to_cancel": list(debts),
            "breakdown": breakdown,
            "total_user1_owes": float(total_user1_owes),
            "total_user2_owes": float(total_user2_owes),
        }

    @staticmethod
    async def cancel_mutual_debts(
        user1: User,
        user2: User,
        base_currency: str,
        session: AsyncSession,
    ) -> Dict:
        """
        Cancel out mutual debts between two users and create a net debt.

        Args:
            user1: First user (initiator)
            user2: Second user
            base_currency: Currency used for calculation ("EUR" or "USD")
            session: Database session

        Returns:
            Dictionary with:
            - cancelled_debts: List of debt IDs that were cancelled
            - net_debt: New net debt created (or None if net is 0)
        """
        # Calculate net debts
        calculation = await DebtService.calculate_net_debts(user1, user2, session, base_currency)

        cancelled_debt_ids = []
        net_debt = None

        # Mark all mutual debts as settled
        for debt in calculation["debts_to_cancel"]:
            debt.is_settled = True
            cancelled_debt_ids.append(debt.id)

        # If net amount is not zero, create a new net debt
        if abs(calculation["net_amount_decimal"]) > Decimal("0.01"):  # Threshold to avoid rounding issues
            if calculation["net_amount"] > 0:
                # user1 owes user2
                creditor = user2
                debtor = user1
                net_amount = calculation["net_amount"]
            else:
                # user2 owes user1
                creditor = user1
                debtor = user2
                net_amount = abs(calculation["net_amount"])

            # Create net debt in base currency
            net_debt = await DebtService.create_debt(
                creditor=creditor,
                debtor=debtor,
                amount=net_amount,
                currency=base_currency,
                category_id=None,  # No category for net debt
                note=f"Net debt after cancelling {len(cancelled_debt_ids)} mutual debt(s)",
                related_transaction_id=None,
                session=session,
            )

        await session.commit()

        logger.info(
            f"Cancelled {len(cancelled_debt_ids)} mutual debts between "
            f"user1={user1.telegram_id} and user2={user2.telegram_id}, "
            f"net_amount={calculation['net_amount']:.2f} {base_currency}"
        )

        return {
            "cancelled_debts": cancelled_debt_ids,
            "net_debt": net_debt,
            "calculation": calculation,
        }

