import uuid
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict
from app.models.operations import DowntimeReason


# --- Production Logs ---
class ProductionLogCreate(BaseModel):
    waste_grade_id: uuid.UUID
    output_weight_kg: Decimal = Field(..., gt=0, decimal_places=2)
    bales_produced: int = Field(default=0, ge=0)


class ProductionLogResponse(BaseModel):
    id: uuid.UUID
    dpr_id: uuid.UUID
    waste_grade_id: uuid.UUID
    output_weight_kg: Decimal
    bales_produced: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Downtime Logs ---
class DowntimeLogCreate(BaseModel):
    reason: DowntimeReason
    duration_minutes: int = Field(..., gt=0)
    equipment_name: str | None = None
    description: str | None = None


class DowntimeLogStandaloneCreate(DowntimeLogCreate):
    plant_id: uuid.UUID | None = None
    log_date: date | None = None


class DowntimeLogResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    dpr_id: uuid.UUID | None = None
    reason: DowntimeReason
    duration_minutes: int
    equipment_name: str | None = None
    description: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Daily Progress Reports ---
class DPRCreate(BaseModel):
    plant_id: uuid.UUID | None = None
    report_date: date
    electricity_kwh: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    diesel_liters: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    strapping_wire_kg: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    total_raw_processed_kg: Decimal = Field(..., gt=0, decimal_places=2)
    total_inert_waste_kg: Decimal = Field(default=Decimal("0.00"), ge=0, decimal_places=2)
    remarks: str | None = None
    production_items: list[ProductionLogCreate] = Field(default_factory=list)
    downtime_logs: list[DowntimeLogCreate] = Field(default_factory=list)


class DPRUpdate(BaseModel):
    electricity_kwh: Decimal | None = Field(None, ge=0, decimal_places=2)
    diesel_liters: Decimal | None = Field(None, ge=0, decimal_places=2)
    strapping_wire_kg: Decimal | None = Field(None, ge=0, decimal_places=2)
    remarks: str | None = None


class DPRResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    report_date: date
    supervisor_id: uuid.UUID
    electricity_kwh: Decimal
    diesel_liters: Decimal
    strapping_wire_kg: Decimal
    total_raw_processed_kg: Decimal
    total_output_produced_kg: Decimal
    total_inert_waste_kg: Decimal
    mass_balance_variance_kg: Decimal
    remarks: str | None = None
    production_items: list[ProductionLogResponse] = Field(default_factory=list)
    downtime_logs: list[DowntimeLogResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)