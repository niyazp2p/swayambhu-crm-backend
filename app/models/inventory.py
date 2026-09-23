import enum
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    ForeignKey,
    Integer,
    UniqueConstraint,
    Index,
    Enum,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class StockMovementType(str, enum.Enum):
    PRODUCTION_INFLOW = "PRODUCTION_INFLOW"
    DISPATCH_OUTFLOW = "DISPATCH_OUTFLOW"
    STOCK_ADJUSTMENT = "STOCK_ADJUSTMENT"
    AUDIT_RECONCILIATION = "AUDIT_RECONCILIATION"


class FinishedGoodsInventory(Base, TimestampMixin):
    """Real-time baled and sorted finished goods stock per plant & waste grade."""
    __tablename__ = "finished_goods_inventory"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    waste_grade_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("waste_grades.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    current_stock_kg: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    bales_in_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships (lazy="select" avoids implicit outer joins during row-locking)
    waste_grade: Mapped["WasteGrade"] = relationship("WasteGrade", lazy="select")
    ledger_entries: Mapped[list["StockLedger"]] = relationship(
        "StockLedger", back_populates="inventory", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("plant_id", "waste_grade_id", name="uq_plant_waste_grade_inventory"),
        Index("idx_plant_grade_stock", "plant_id", "waste_grade_id", "current_stock_kg"),
    )


class StockLedger(Base, TimestampMixin):
    """Immutable passbook ledger tracking every single KG change in inventory."""
    __tablename__ = "stock_ledgers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    inventory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("finished_goods_inventory.id", ondelete="CASCADE"), nullable=False, index=True
    )
    movement_type: Mapped[StockMovementType] = mapped_column(
        Enum(StockMovementType, name="stock_movement_type_enum"), nullable=False, index=True
    )
    
    # Delta applied (+ for inflow, - for outflow/shrinkage)
    delta_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    delta_bales: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Balance snapshots after mutation
    balance_weight_kg: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_bales: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Upstream source tracking
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True) # DPR ID or Dispatch ID
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    inventory: Mapped["FinishedGoodsInventory"] = relationship("FinishedGoodsInventory", back_populates="ledger_entries")