"""global market fields on orm_reports

Revision ID: 002_global_market_fields
Revises: 001_initial_schema
Create Date: 2026-09-23 13:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_global_market_fields"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "orm_reports",
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="unknown"),
    )
    op.add_column("orm_reports", sa.Column("country", sa.String(length=64), nullable=True))
    op.add_column("orm_reports", sa.Column("city", sa.String(length=64), nullable=True))
    op.add_column("orm_reports", sa.Column("neighborhood", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("orm_reports", "neighborhood")
    op.drop_column("orm_reports", "city")
    op.drop_column("orm_reports", "country")
    op.drop_column("orm_reports", "currency")
