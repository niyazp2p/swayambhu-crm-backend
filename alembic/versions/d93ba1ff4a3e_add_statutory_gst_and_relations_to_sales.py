"""add_statutory_gst_and_relations_to_sales

Revision ID: d93ba1ff4a3e
Revises: e118a3ade113
Create Date: 2026-09-13 16:31:17.121287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd93ba1ff4a3e'
down_revision: Union[str, Sequence[str], None] = 'e118a3ade113'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with safe backfills for buyers and dispatch_orders."""
    
    # -------------------------------------------------------------------------
    # 1. Buyers Table (Add columns, backfill, enforce constraints)
    # -------------------------------------------------------------------------
    op.add_column('buyers', sa.Column('pan_number', sa.String(length=20), nullable=True))
    op.add_column('buyers', sa.Column('shipping_address', sa.Text(), nullable=True))
    op.add_column('buyers', sa.Column('state_code', sa.String(length=2), nullable=True))

    # Backfill state_code with Uttarakhand default ('05') for existing buyers
    op.execute("UPDATE buyers SET state_code = '05' WHERE state_code IS NULL")

    # Enforce NOT NULL and default
    op.alter_column('buyers', 'state_code', nullable=False, server_default=sa.text("'05'"))
    op.create_index(op.f('ix_buyers_gstin'), 'buyers', ['gstin'], unique=False)

    # -------------------------------------------------------------------------
    # 2. Dispatch Orders Table (Add transport & statutory tax columns)
    # -------------------------------------------------------------------------
    op.add_column('dispatch_orders', sa.Column('transporter_name', sa.String(length=150), nullable=True))
    op.add_column('dispatch_orders', sa.Column('eway_bill_number', sa.String(length=50), nullable=True))

    # Add numeric tax columns as nullable first
    op.add_column('dispatch_orders', sa.Column('taxable_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('cgst_rate', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('cgst_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('sgst_rate', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('sgst_amount', sa.Numeric(precision=12, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('igst_rate', sa.Numeric(precision=5, scale=2), nullable=True))
    op.add_column('dispatch_orders', sa.Column('igst_amount', sa.Numeric(precision=12, scale=2), nullable=True))

    # Backfill existing dispatches: map historical total_amount to taxable_amount, set tax components to 0.00
    op.execute("""
        UPDATE dispatch_orders
        SET taxable_amount = total_amount,
            cgst_rate = 0.00,
            cgst_amount = 0.00,
            sgst_rate = 0.00,
            sgst_amount = 0.00,
            igst_rate = 0.00,
            igst_amount = 0.00
        WHERE taxable_amount IS NULL;
    """)

    # Enforce NOT NULL constraints
    op.alter_column('dispatch_orders', 'taxable_amount', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'cgst_rate', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'cgst_amount', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'sgst_rate', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'sgst_amount', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'igst_rate', nullable=False, server_default=sa.text('0.00'))
    op.alter_column('dispatch_orders', 'igst_amount', nullable=False, server_default=sa.text('0.00'))

    # Indexes
    op.create_index(op.f('ix_dispatch_orders_buyer_id'), 'dispatch_orders', ['buyer_id'], unique=False)
    op.create_index(op.f('ix_dispatch_orders_payment_status'), 'dispatch_orders', ['payment_status'], unique=False)
    op.create_index(op.f('ix_dispatch_orders_vehicle_number'), 'dispatch_orders', ['vehicle_number'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_dispatch_orders_vehicle_number'), table_name='dispatch_orders')
    op.drop_index(op.f('ix_dispatch_orders_payment_status'), table_name='dispatch_orders')
    op.drop_index(op.f('ix_dispatch_orders_buyer_id'), table_name='dispatch_orders')
    op.drop_column('dispatch_orders', 'igst_amount')
    op.drop_column('dispatch_orders', 'igst_rate')
    op.drop_column('dispatch_orders', 'sgst_amount')
    op.drop_column('dispatch_orders', 'sgst_rate')
    op.drop_column('dispatch_orders', 'cgst_amount')
    op.drop_column('dispatch_orders', 'cgst_rate')
    op.drop_column('dispatch_orders', 'taxable_amount')
    op.drop_column('dispatch_orders', 'eway_bill_number')
    op.drop_column('dispatch_orders', 'transporter_name')
    op.drop_index(op.f('ix_buyers_gstin'), table_name='buyers')
    op.drop_column('buyers', 'shipping_address')
    op.drop_column('buyers', 'state_code')
    op.drop_column('buyers', 'pan_number')