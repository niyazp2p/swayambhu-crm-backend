import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models.sales import DispatchStatus, PaymentStatus


# --- Shared Sub-Schemas for Responsive UI Serialization ---
class PlantSummary(BaseModel):
    id: uuid.UUID
    name: str
    code: str

    model_config = ConfigDict(from_attributes=True)


class WasteGradeSummary(BaseModel):
    id: uuid.UUID
    category_name: str
    grade_code: str
    current_rate_per_kg: Decimal

    model_config = ConfigDict(from_attributes=True)


class BuyerBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    gstin: str | None = Field(None, max_length=20)
    pan_number: str | None = Field(None, max_length=20)
    state_code: str = Field(default="05", min_length=2, max_length=2)
    contact_person: str | None = Field(None, max_length=100)
    contact_phone: str = Field(..., min_length=8, max_length=20)
    billing_address: str
    shipping_address: str | None = None


class BuyerCreate(BuyerBase):
    pass


class BuyerUpdate(BaseModel):
    name: str | None = None
    gstin: str | None = None
    pan_number: str | None = None
    contact_person: str | None = None
    contact_phone: str | None = None
    billing_address: str | None = None
    shipping_address: str | None = None
    is_active: bool | None = None


class BuyerResponse(BuyerBase):
    id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Dispatch Schemas ---
class DispatchOrderCreate(BaseModel):
    buyer_id: uuid.UUID
    waste_grade_id: uuid.UUID
    vehicle_number: str = Field(..., min_length=4, max_length=30)
    driver_name: str | None = Field(None, max_length=100)
    driver_phone: str | None = Field(None, max_length=20)
    transporter_name: str | None = Field(None, max_length=150)
    eway_bill_number: str | None = Field(None, max_length=50)
    tare_weight_kg: Decimal = Field(..., ge=0, decimal_places=2)
    gross_weight_kg: Decimal = Field(..., gt=0, decimal_places=2)
    bales_count: int = Field(default=0, ge=0)
    rate_per_kg: Decimal = Field(..., gt=0, decimal_places=2)
    gst_rate_percent: Decimal = Field(default=Decimal("18.00"), ge=0, le=28, decimal_places=2)
    is_interstate: bool = Field(default=False)
    dispatch_date: date | None = None
    remarks: str | None = None


class DispatchOrderResponse(BaseModel):
    id: uuid.UUID
    dispatch_number: str
    plant_id: uuid.UUID
    buyer_id: uuid.UUID
    waste_grade_id: uuid.UUID
    vehicle_number: str
    driver_name: str | None = None
    driver_phone: str | None = None
    transporter_name: str | None = None
    eway_bill_number: str | None = None
    tare_weight_kg: Decimal
    gross_weight_kg: Decimal
    net_weight_kg: Decimal
    bales_count: int
    rate_per_kg: Decimal
    taxable_amount: Decimal
    cgst_rate: Decimal
    cgst_amount: Decimal
    sgst_rate: Decimal
    sgst_amount: Decimal
    igst_rate: Decimal
    igst_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    status: DispatchStatus
    payment_status: PaymentStatus
    dispatch_date: date
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime

    # Nested Models for single-flight frontend rendering
    buyer: BuyerResponse | None = None
    plant: PlantSummary | None = None
    waste_grade: WasteGradeSummary | None = None

    model_config = ConfigDict(from_attributes=True)


class PaymentUpdate(BaseModel):
    payment_amount: Decimal = Field(..., gt=0, decimal_places=2)
    payment_reference: str | None = Field(None, max_length=100, description="UTR, Cheque, or Cash Reference")