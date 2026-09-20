"""
SQLAlchemy ORM model for regional material price benchmarks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class PriceHistory(Base, TimestampMixin):
    __tablename__ = "orm_price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    median_price_per_kg: Mapped[float] = mapped_column(Float, nullable=False)
    min_price_per_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_price_per_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PriceHistory material={self.material_type} loc='{self.location}' "
            f"median={self.median_price_per_kg} count={self.sample_count}>"
        )
