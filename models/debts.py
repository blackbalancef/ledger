"""Debt model for tracking split bills and debts between users."""

import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    UUID,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    Numeric,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class Debt(Base):
    __tablename__ = "debts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    
    # Creditor is the person who is owed money (paid the bill)
    creditor_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Debtor is the person who owes money (didn't pay)
    debtor_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    
    # Converted amounts at debt creation time
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    
    # Exchange rates at debt creation time
    fx_rate_to_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Link to the original transaction that created this debt
    related_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )
    
    is_settled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Relationships
    creditor: Mapped["User"] = relationship("User", foreign_keys=[creditor_user_id], backref="creditor_debts")
    debtor: Mapped["User"] = relationship("User", foreign_keys=[debtor_user_id], backref="debtor_debts")
    category: Mapped["Category"] = relationship("Category")
    related_transaction: Mapped["Transaction"] = relationship("Transaction", foreign_keys=[related_transaction_id])

    def __repr__(self):
        return (
            f"<Debt(id={self.id}, creditor={self.creditor_user_id}, debtor={self.debtor_user_id}, "
            f"amount={self.amount_minor}, currency={self.currency}, settled={self.is_settled})>"
        )

    @property
    def amount(self) -> Decimal:
        """Get amount in major currency units (e.g., dollars, not cents)"""
        return Decimal(self.amount_minor) / 100

    @staticmethod
    def to_minor_units(amount: float | Decimal, currency: str = "RSD") -> int:
        """Convert amount to minor units (cents)"""
        return int(Decimal(str(amount)) * 100)

