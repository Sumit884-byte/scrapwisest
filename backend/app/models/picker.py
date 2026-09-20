"""
SQLAlchemy ORM model for waste pickers.
"""

from __future__ import annotations

from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Picker(Base, TimestampMixin):
    __tablename__ = "orm_pickers"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    default_location: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    preferred_language: Mapped[Optional[str]] = mapped_column(String(20), default="en", nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<Picker id='{self.id}' loc='{self.default_location}' lang='{self.preferred_language}'>"
