from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import String, Date, DateTime, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (
        UniqueConstraint("currency", "base", "date", name="uix_currency_base_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, index=True)
    base: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    def __repr__(self):
        return (
            f"<FxRate(currency={self.currency}, base={self.base}, "
            f"rate={self.rate}, date={self.date})>"
        )

