"""refactor_operations_and_downtime_architecture

Revision ID: e118a3ade113
Revises: f1e5cec1ffab
Create Date: 2026-09-13 15:23:37.001299

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e118a3ade113'
down_revision: Union[str, Sequence[str], None] = 'f1e5cec1ffab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema with deduplication and backfilled plant_id."""

    # -------------------------------------------------------------------------
    # 1. Deduplicate daily_progress_reports before applying unique constraint
    # -------------------------------------------------------------------------
    op.execute("""
        DELETE FROM daily_progress_reports
        WHERE id NOT IN (
            SELECT id FROM (
                SELECT DISTINCT ON (plant_id, report_date) id
                FROM daily_progress_reports
                ORDER BY plant_id, report_date, created_at DESC
            ) keep_rows
        );
    """)

    op.create_index('ix_dpr_plant_date', 'daily_progress_reports', ['plant_id', 'report_date'], unique=False)
    op.create_unique_constraint('uq_plant_report_date', 'daily_progress_reports', ['plant_id', 'report_date'])

    # -------------------------------------------------------------------------
    # 2. Add plant_id to downtime_logs safely (Nullable -> Backfill -> NOT NULL)
    # -------------------------------------------------------------------------
    op.add_column('downtime_logs', sa.Column('plant_id', sa.UUID(), nullable=True))
    op.add_column('downtime_logs', sa.Column('equipment_name', sa.String(length=100), nullable=True))

    # Backfill plant_id from parent daily_progress_reports for existing logs
    op.execute("""
        UPDATE downtime_logs
        SET plant_id = daily_progress_reports.plant_id
        FROM daily_progress_reports
        WHERE downtime_logs.dpr_id = daily_progress_reports.id
        AND downtime_logs.plant_id IS NULL;
    """)

    # Fallback in case of orphaned downtime logs without a parent DPR
    op.execute("""
        UPDATE downtime_logs
        SET plant_id = (SELECT id FROM plants LIMIT 1)
        WHERE plant_id IS NULL;
    """)

    # Enforce NOT NULL after backfilling
    op.alter_column('downtime_logs', 'plant_id', nullable=False)

    # -------------------------------------------------------------------------
    # 3. Alter existing columns, foreign keys, and indexes
    # -------------------------------------------------------------------------
    op.alter_column(
        'downtime_logs',
        'dpr_id',
        existing_type=sa.UUID(),
        nullable=True,
    )
    op.create_index(op.f('ix_downtime_logs_plant_id'), 'downtime_logs', ['plant_id'], unique=False)
    op.create_index(op.f('ix_downtime_logs_reason'), 'downtime_logs', ['reason'], unique=False)
    op.create_foreign_key(
        'fk_downtime_logs_plant_id_plants',
        'downtime_logs',
        'plants',
        ['plant_id'],
        ['id'],
        ondelete='RESTRICT',
    )
    op.create_index(op.f('ix_production_logs_waste_grade_id'), 'production_logs', ['waste_grade_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_production_logs_waste_grade_id'), table_name='production_logs')
    op.drop_constraint('fk_downtime_logs_plant_id_plants', 'downtime_logs', type_='foreignkey')
    op.drop_index(op.f('ix_downtime_logs_reason'), table_name='downtime_logs')
    op.drop_index(op.f('ix_downtime_logs_plant_id'), table_name='downtime_logs')
    op.alter_column(
        'downtime_logs',
        'dpr_id',
        existing_type=sa.UUID(),
        nullable=False,
    )
    op.drop_column('downtime_logs', 'equipment_name')
    op.drop_column('downtime_logs', 'plant_id')
    op.drop_constraint('uq_plant_report_date', 'daily_progress_reports', type_='unique')
    op.drop_index('ix_dpr_plant_date', table_name='daily_progress_reports')