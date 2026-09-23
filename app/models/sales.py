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
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DispatchStatus(str, enum.Enum):
    PENDING = "PENDING"
    WEIGHED_OUT = "WEIGHED_OUT"
    DISPATCHED = "DISPATCHED"
    CANCELLED = "CANCELLED"


class PaymentStatus(str, enum.Enum):
    UNPAID = "UNPAID"
    PARTIAL = "PARTIAL"
    PAID = "PAID"


class Buyer(Base, TimestampMixin):
    """Offtaker / Buyer companies purchasing processed/baled scrap."""
    __tablename__ = "buyers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    gstin: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    pan_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False, default="05")  # e.g., '05' for Uttarakhand, '10' for Bihar
    contact_person: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    billing_address: Mapped[str] = mapped_column(Text, nullable=False)
    shipping_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    dispatches: Mapped[list["DispatchOrder"]] = relationship("DispatchOrder", back_populates="buyer")


class DispatchOrder(Base, TimestampMixin):
    """Outward truck dispatch, weighbridge gate pass, and GST invoice tracking."""
    __tablename__ = "dispatch_orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dispatch_number: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    buyer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buyers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    waste_grade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waste_grades.id", ondelete="RESTRICT"), nullable=False
    )
    operator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Transport Details
    vehicle_number: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    driver_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    driver_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    transporter_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    eway_bill_number: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Weighbridge Measurements
    tare_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    gross_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bales_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Commercial Valuation & Statutory Taxes
    rate_per_kg: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    cgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    sgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    igst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"), nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"), nullable=False)

    status: Mapped[DispatchStatus] = mapped_column(
        Enum(DispatchStatus, name="dispatch_status_enum"), default=DispatchStatus.DISPATCHED, nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status_enum"), default=PaymentStatus.UNPAID, nullable=False, index=True
    )

    dispatch_date: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    buyer: Mapped["Buyer"] = relationship("Buyer", back_populates="dispatches", lazy="selectin")
    plant: Mapped["Plant"] = relationship("Plant", lazy="selectin")
    waste_grade: Mapped["WasteGrade"] = relationship("WasteGrade", lazy="selectin")