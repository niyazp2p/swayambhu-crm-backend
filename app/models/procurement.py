import enum
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    Enum,
    ForeignKey,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class VendorType(str, enum.Enum):
    KABADIWALA = "KABADIWALA"
    INDUSTRIAL_GENERATOR = "INDUSTRIAL_GENERATOR"
    MUNICIPAL = "MUNICIPAL"
    OTHER = "OTHER"


class BatchStage(str, enum.Enum):
    RAW = "RAW"
    SORTED = "SORTED"
    PROCESSED_BALED = "PROCESSED_BALED"
    FINISHED_GOODS = "FINISHED_GOODS"


class DeductionMethod(str, enum.Enum):
    FLAT_PERCENTAGE = "FLAT_PERCENTAGE"
    SLAB = "SLAB"
    MANUAL_ASSESSMENT = "MANUAL_ASSESSMENT"


class Vendor(Base, TimestampMixin):
    """Scrap aggregators, kabadiwalas, and commercial suppliers."""
    __tablename__ = "vendors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    vendor_type: Mapped[VendorType] = mapped_column(
        Enum(VendorType, name="vendor_type_enum"), nullable=False, default=VendorType.KABADIWALA
    )
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships
    grns: Mapped[list["GRNRecord"]] = relationship("GRNRecord", back_populates="vendor")


class WasteGrade(Base, TimestampMixin):
    """Scrap classification catalog and per-kg intake pricing."""
    __tablename__ = "waste_grades"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g., Plastic, Metal, Paper
    grade_code: Mapped[str] = mapped_column(String(50), nullable=False)       # e.g., HDPE, PET, Ferrous
    current_rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    deduction_method: Mapped[DeductionMethod] = mapped_column(
        Enum(DeductionMethod, name="deduction_method_enum"),
        default=DeductionMethod.FLAT_PERCENTAGE,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GRNRecord(Base, TimestampMixin):
    """Goods Receipt Note for raw material inward intake."""
    __tablename__ = "grn_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    grn_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vendors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    waste_grade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waste_grades.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vehicle_number: Mapped[str] = mapped_column(String(30), nullable=False)

    # Weights (in Kilograms)
    gross_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tare_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Deductions
    moisture_percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    contamination_deduction_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    accepted_net_weight: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Financials (Snapshot at intake time)
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    total_payable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    payment_status: Mapped[str] = mapped_column(String(20), default="UNPAID", nullable=False)
    amount_settled: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    # Audit & Overrides
    is_manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    load_photo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Relationships
    vendor: Mapped["Vendor"] = relationship("Vendor", back_populates="grns")
    batch: Mapped["Batch | None"] = relationship("Batch", back_populates="grn", uselist=False)


class Batch(Base, TimestampMixin):
    """Warehouse inventory batch lifecycle."""
    __tablename__ = "batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    batch_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    grn_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grn_records.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[BatchStage] = mapped_column(
        Enum(BatchStage, name="batch_stage_enum"), default=BatchStage.RAW, nullable=False
    )
    yard_location: Mapped[str | None] = mapped_column(String(50), nullable=True)
    initial_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    current_quantity_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    grn: Mapped["GRNRecord | None"] = relationship("GRNRecord", back_populates="batch")