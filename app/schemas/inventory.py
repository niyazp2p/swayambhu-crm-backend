import uuid
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.inventory import StockMovementType


class InventoryStockResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    waste_grade_id: uuid.UUID
    waste_grade_code: str
    category_name: str
    current_stock_kg: Decimal = Field(..., decimal_places=2)
    bales_in_stock: int
    current_valuation_inr: Decimal = Field(..., decimal_places=2)
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedStockResponse(BaseModel):
    total_grades: int
    total_stock_kg: Decimal = Field(..., decimal_places=2)
    total_bales: int
    total_valuation_inr: Decimal = Field(..., decimal_places=2)
    items: list[InventoryStockResponse]


class StockAdjustmentCreate(BaseModel):
    waste_grade_id: uuid.UUID
    adjusted_weight_kg: Decimal = Field(..., description="Absolute verified physical weight in KG", ge=0)
    adjusted_bales: int = Field(..., description="Absolute count of verified physical bales", ge=0)
    remarks: str = Field(..., min_length=5, description="Audit reason for stock shrinkage or discrepancy")


class StockLedgerResponse(BaseModel):
    id: uuid.UUID
    movement_type: StockMovementType
    delta_weight_kg: Decimal
    delta_bales: int
    balance_weight_kg: Decimal
    balance_bales: int
    reference_id: uuid.UUID | None
    remarks: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)