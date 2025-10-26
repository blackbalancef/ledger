import enum
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    UUID,
    BigInteger,
    String,
    Text,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base


class TransactionTypeEnum(str, enum.Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"
    REVERSAL = "REVERSAL"
    SETTLEMENT = "SETTLEMENT"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transaction_type: Mapped[TransactionTypeEnum] = mapped_column(
        Enum(TransactionTypeEnum), nullable=False, index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    
    # Converted amounts
    amount_eur: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    
    # Exchange rates at transaction time
    fx_rate_to_eur: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fx_rate_to_usd: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    at_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    # Optional link to a debt for SETTLEMENT transactions
    related_debt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("debts.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="transactions")
    category: Mapped["Category"] = relationship("Category", back_populates="transactions")
    related_debt: Mapped["Debt"] = relationship("Debt", foreign_keys=[related_debt_id])

    def __repr__(self):
        return (
            f"<Transaction(id={self.id}, type={self.transaction_type.value}, "
            f"amount={self.amount_minor}, currency={self.currency})>"
        )

    @property
    def amount(self) -> Decimal:
        """Get amount in major currency units (e.g., dollars, not cents)"""
        return Decimal(self.amount_minor) / 100

    @staticmethod
    def to_minor_units(amount: float | Decimal, currency: str = "RSD") -> int:
        """Convert amount to minor units (cents)"""
        # For currencies without minor units (like some Asian currencies), adjust accordingly
        return int(Decimal(str(amount)) * 100)

