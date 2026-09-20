"""initial_schema

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create orm_pickers table
    op.create_table(
        'orm_pickers',
        sa.Column('id', sa.String(length=100), primary_key=True),
        sa.Column('default_location', sa.String(length=100), nullable=True),
        sa.Column('preferred_language', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create orm_reports table
    op.create_table(
        'orm_reports',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('material_type', sa.String(length=50), nullable=False),
        sa.Column('quantity_kg', sa.Float(), nullable=False),
        sa.Column('price_paid_pkr', sa.Float(), nullable=False),
        sa.Column('price_paid_pkr_per_kg', sa.Float(), nullable=False),
        sa.Column('location', sa.String(length=100), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('needs_confirmation', sa.Boolean(), nullable=False),
        sa.Column('confirmation_reason', sa.String(length=255), nullable=True),
        sa.Column('picker_id', sa.String(length=100), nullable=True),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_orm_reports_material_type', 'orm_reports', ['material_type'])
    op.create_index('ix_orm_reports_location', 'orm_reports', ['location'])
    op.create_index('ix_orm_reports_price_per_kg', 'orm_reports', ['price_paid_pkr_per_kg'])
    op.create_index('ix_orm_reports_picker_id', 'orm_reports', ['picker_id'])

    # Create orm_price_history table
    op.create_table(
        'orm_price_history',
        sa.Column('id', sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column('material_type', sa.String(length=50), nullable=False),
        sa.Column('location', sa.String(length=100), nullable=False),
        sa.Column('median_price_per_kg', sa.Float(), nullable=False),
        sa.Column('min_price_per_kg', sa.Float(), nullable=True),
        sa.Column('max_price_per_kg', sa.Float(), nullable=True),
        sa.Column('sample_count', sa.Integer(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_orm_price_history_material', 'orm_price_history', ['material_type'])
    op.create_index('ix_orm_price_history_location', 'orm_price_history', ['location'])


def downgrade() -> None:
    op.drop_table('orm_price_history')
    op.drop_table('orm_reports')
    op.drop_table('orm_pickers')
