import enum
import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Enum,
    ForeignKey,
    Date,
    Integer,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DowntimeReason(str, enum.Enum):
    MACHINE_BREAKDOWN = "MACHINE_BREAKDOWN"
    POWER_OUTAGE = "POWER_OUTAGE"
    FEEDSTOCK_SHORTAGE = "FEEDSTOCK_SHORTAGE"
    MAINTENANCE = "MAINTENANCE"
    LABOR_UNAVAILABLE = "LABOR_UNAVAILABLE"
    OTHER = "OTHER"


class DailyProgressReport(Base, TimestampMixin):
    """Master record for plant-level daily operational summary."""
    __tablename__ = "daily_progress_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    supervisor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Utilities & Consumables
    electricity_kwh: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    diesel_liters: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    strapping_wire_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    # Reconciliations & Mass Balance
    total_raw_processed_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_output_produced_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_inert_waste_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    mass_balance_variance_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant")
    supervisor: Mapped["User"] = relationship("User")
    production_items: Mapped[list["ProductionLog"]] = relationship(
        "ProductionLog", back_populates="dpr", cascade="all, delete-orphan"
    )
    downtime_logs: Mapped[list["DowntimeLog"]] = relationship(
        "DowntimeLog", back_populates="dpr", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("plant_id", "report_date", name="uq_plant_report_date"),
        Index("ix_dpr_plant_date", "plant_id", "report_date"),
    )


class ProductionLog(Base, TimestampMixin):
    """Detailed production outputs per waste category/grade."""
    __tablename__ = "production_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dpr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_progress_reports.id", ondelete="CASCADE"), nullable=False, index=True
    )
    waste_grade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waste_grades.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    output_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bales_produced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    dpr: Mapped["DailyProgressReport"] = relationship("DailyProgressReport", back_populates="production_items")
    waste_grade: Mapped["WasteGrade"] = relationship("WasteGrade")


class DowntimeLog(Base, TimestampMixin):
    """Operational stoppage records (tied to DPR or logged independently)."""
    __tablename__ = "downtime_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dpr_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_progress_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reason: Mapped[DowntimeReason] = mapped_column(
        Enum(DowntimeReason, name="downtime_reason_enum"), nullable=False, index=True
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    equipment_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    dpr: Mapped["DailyProgressReport | None"] = relationship("DailyProgressReport", back_populates="downtime_logs")