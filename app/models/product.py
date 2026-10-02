import enum
import uuid
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    Enum,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class WeightUnit(str, enum.Enum):
    KG = "KG"
    GRAMS = "GRAMS"
    MT = "MT"


class MaterialCategory(Base, TimestampMixin):
    """Primary Material Category (e.g., Plastic, Composite, Metal)."""
    __tablename__ = "material_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    sub_categories: Mapped[list["MaterialSubCategory"]] = relationship(
        "MaterialSubCategory", back_populates="category", cascade="all, delete-orphan"
    )


class MaterialSubCategory(Base, TimestampMixin):
    """Material Subcategory (e.g., Polyal, HM, Tube, LDPE, HDPE)."""
    __tablename__ = "material_sub_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_categories.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True) # e.g., SUB_POLYAL, SUB_HM
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    category: Mapped["MaterialCategory"] = relationship("MaterialCategory", back_populates="sub_categories")
    product_materials: Mapped[list["ProductMaterialComposition"]] = relationship(
        "ProductMaterialComposition", back_populates="sub_category"
    )


class Product(Base, TimestampMixin):
    """Finished upcycled products (e.g., Eco-Board, Handwashing Station, School Desk)."""
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    sku: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions: Mapped[str | None] = mapped_column(String(100), nullable=True) # e.g., 8x4 ft x 12mm
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Stock & Quantity Tracking
    total_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unit_measure: Mapped[str] = mapped_column(String(30), default="PIECES", nullable=False) # PIECES / UNITS

    # Aggregate Weight (computed or benchmarked)
    total_weight_kg: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("0.000"), nullable=False)

    # Relationships
    materials_used: Mapped[list["ProductMaterialComposition"]] = relationship(
        "ProductMaterialComposition",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProductMaterialComposition(Base, TimestampMixin):
    """Breakdown of raw scrap materials consumed per unit product."""
    __tablename__ = "product_material_compositions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sub_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("material_sub_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Weight Formulation
    weight: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    unit: Mapped[WeightUnit] = mapped_column(
        Enum(WeightUnit, name="weight_unit_enum"), default=WeightUnit.KG, nullable=False
    )
    percentage_share: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="materials_used")
    sub_category: Mapped["MaterialSubCategory"] = relationship("MaterialSubCategory", back_populates="product_materials", lazy="joined")

    __table_args__ = (
        UniqueConstraint("product_id", "sub_category_id", name="uq_product_material_subcategory"),
    )