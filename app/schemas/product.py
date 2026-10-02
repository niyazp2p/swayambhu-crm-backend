import uuid
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.product import WeightUnit


# --- Material Subcategories ---
class MaterialSubCategoryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    code: str = Field(..., min_length=2, max_length=50)
    description: str | None = None


class MaterialSubCategoryCreate(MaterialSubCategoryBase):
    category_id: uuid.UUID


class MaterialSubCategoryResponse(MaterialSubCategoryBase):
    id: uuid.UUID
    category_id: uuid.UUID
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Material Compositions & Weights ---
class ProductMaterialCreate(BaseModel):
    sub_category_id: uuid.UUID
    weight: Decimal = Field(..., gt=0, decimal_places=3, description="Weight per unit item")
    unit: WeightUnit = WeightUnit.KG


class ProductMaterialResponse(BaseModel):
    id: uuid.UUID
    sub_category_id: uuid.UUID
    sub_category_name: str
    sub_category_code: str
    weight: Decimal
    unit: WeightUnit
    percentage_share: Decimal | None = None

    model_config = ConfigDict(from_attributes=True)


# --- Products ---
class ProductCreate(BaseModel):
    sku: str = Field(..., min_length=3, max_length=50)
    name: str = Field(..., min_length=2, max_length=200)
    description: str | None = None
    dimensions: str | None = None
    total_quantity: int = Field(default=0, ge=0)
    unit_measure: str = "PIECES"
    materials: list[ProductMaterialCreate] = Field(default_factory=list)


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    dimensions: str | None = None
    unit_measure: str | None = None
    is_active: bool | None = None


class QuantityUpdate(BaseModel):
    total_quantity: int = Field(..., ge=0)


class ProductResponse(BaseModel):
    id: uuid.UUID
    sku: str
    name: str
    description: str | None = None
    dimensions: str | None = None
    total_quantity: int
    unit_measure: str
    total_weight_kg: Decimal
    is_active: bool
    materials_used: list[ProductMaterialResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)