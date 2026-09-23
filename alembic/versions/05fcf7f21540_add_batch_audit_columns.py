"""add_batch_audit_columns

Revision ID: 05fcf7f21540
Revises: b529d644e3a3
Create Date: 2026-09-13 13:15:21.922270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '05fcf7f21540'
down_revision: Union[str, Sequence[str], None] = 'b529d644e3a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with backfilled non-null audit columns."""
    
    # ---------------------------------------------------------
    # 1. Batches Table
    # ---------------------------------------------------------
    # Step A: Add as nullable
    op.add_column('batches', sa.Column('initial_quantity_kg', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('batches', sa.Column('is_consumed', sa.Boolean(), nullable=True))

    # Step B: Backfill existing records
    op.execute("UPDATE batches SET initial_quantity_kg = current_quantity_kg WHERE initial_quantity_kg IS NULL")
    op.execute("UPDATE batches SET is_consumed = FALSE WHERE is_consumed IS NULL")

    # Step C: Enforce NOT NULL constraints
    op.alter_column('batches', 'initial_quantity_kg', nullable=False)
    op.alter_column('batches', 'is_consumed', nullable=False, server_default=sa.text('false'))

    # ---------------------------------------------------------
    # 2. GRN Records Table
    # ---------------------------------------------------------
    # Step A: Add as nullable
    op.add_column('grn_records', sa.Column('payment_status', sa.String(length=20), nullable=True))
    op.add_column('grn_records', sa.Column('amount_settled', sa.Numeric(precision=12, scale=2), nullable=True))

    # Step B: Backfill existing intake slips
    op.execute("UPDATE grn_records SET payment_status = 'UNPAID' WHERE payment_status IS NULL")
    op.execute("UPDATE grn_records SET amount_settled = 0.00 WHERE amount_settled IS NULL")

    # Step C: Enforce NOT NULL constraints
    op.alter_column('grn_records', 'payment_status', nullable=False, server_default=sa.text("'UNPAID'"))
    op.alter_column('grn_records', 'amount_settled', nullable=False, server_default=sa.text('0.00'))

    # ---------------------------------------------------------
    # 3. Vendors Table (These are already nullable=True)
    # ---------------------------------------------------------
    op.add_column('vendors', sa.Column('gstin', sa.String(length=20), nullable=True))
    op.add_column('vendors', sa.Column('pan_number', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('vendors', 'pan_number')
    op.drop_column('vendors', 'gstin')
    op.drop_column('grn_records', 'amount_settled')
    op.drop_column('grn_records', 'payment_status')
    op.drop_column('batches', 'is_consumed')
    op.drop_column('batches', 'initial_quantity_kg')