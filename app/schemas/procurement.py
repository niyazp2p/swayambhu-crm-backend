import uuid
from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

from app.models.procurement import VendorType, BatchStage, DeductionMethod

RAW_MATERIAL_TYPES = Literal[
    "MLP plastic",
    "HM plastic",
    "Polyal",
    "polyster roll",
    "tube",
    "Iron",
]

PAYMENT_STATUS_TYPES = Literal["UNPAID", "PAID"]


class VendorCreate(BaseModel):
    name: str
    vendor_type: VendorType = VendorType.KABADIWALA
    contact_phone: str | None = None
    address: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    gstin: str | None = None
    pan_number: str | None = None


class VendorResponse(VendorCreate):
    id: uuid.UUID
    plant_id: uuid.UUID
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WasteGradeCreate(BaseModel):
    category_name: str
    grade_code: str
    current_rate_per_kg: Decimal = Field(..., gt=0)
    deduction_method: DeductionMethod = DeductionMethod.FLAT_PERCENTAGE


class WasteGradeResponse(WasteGradeCreate):
    id: uuid.UUID
    plant_id: uuid.UUID
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class GRNCreate(BaseModel):
    vendor_id: uuid.UUID
    waste_grade_id: uuid.UUID
    vehicle_number: str
    raw_material: RAW_MATERIAL_TYPES = "MLP plastic"
    payment_status: PAYMENT_STATUS_TYPES = "UNPAID"
    gross_weight: Decimal = Field(..., gt=0)
    tare_weight: Decimal = Field(..., ge=0)
    moisture_percentage: Decimal = Field(default=Decimal("0.00"), ge=0, le=100)
    contamination_deduction_kg: Decimal = Field(default=Decimal("0.00"), ge=0)
    is_manual_override: bool = False
    override_reason: str | None = None
    load_photo_url: str | None = None


class GRNResponse(BaseModel):
    id: uuid.UUID
    grn_number: str
    plant_id: uuid.UUID
    vendor_id: uuid.UUID
    waste_grade_id: uuid.UUID
    vehicle_number: str
    raw_material: str
    payment_status: str
    amount_settled: Decimal
    gross_weight: Decimal
    tare_weight: Decimal
    net_weight: Decimal
    accepted_net_weight: Decimal
    rate_per_kg: Decimal
    total_payable_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    batch_code: str
    grn_id: uuid.UUID | None = None
    stage: BatchStage
    yard_location: str | None = None
    initial_quantity_kg: Decimal
    current_quantity_kg: Decimal
    is_consumed: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BatchUpdate(BaseModel):
    stage: BatchStage | None = None
    yard_location: str | None = None