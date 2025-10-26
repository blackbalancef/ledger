import enum
from sqlalchemy import String, Enum, Boolean, BigInteger, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import List, Optional

from core.db import Base


class TransactionType(str, enum.Enum):
    EXPENSE = "EXPENSE"
    INCOME = "INCOME"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        Index('ix_categories_user_type_archived', 'user_id', 'transaction_type', 'is_archived'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    icon: Mapped[str] = mapped_column(String(10), nullable=False, default="📝")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    
    # User-specific fields
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    transactions: Mapped[List["Transaction"]] = relationship(
        "Transaction", back_populates="category"
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="categories")

    @property
    def is_template(self) -> bool:
        """Check if category is a default template (not user-specific)."""
        return self.user_id is None

    def __repr__(self):
        return f"<Category(id={self.id}, name={self.name}, transaction_type={self.transaction_type.value}, user_id={self.user_id})>"

