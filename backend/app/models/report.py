"""
SQLAlchemy ORM model for waste sale reports.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Report(Base, TimestampMixin):
    __tablename__ = "orm_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    material_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    price_paid_pkr: Mapped[float] = mapped_column(Float, nullable=False)
    price_paid_pkr_per_kg: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    location: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    needs_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmation_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    picker_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Report id={self.id} material={self.material_type} "
            f"qty={self.quantity_kg}kg price/kg={self.price_paid_pkr_per_kg} "
            f"loc='{self.location}'>"
        )
