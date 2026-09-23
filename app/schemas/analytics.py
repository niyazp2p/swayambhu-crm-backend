from datetime import date
from decimal import Decimal
from pydantic import BaseModel


class DowntimeMetric(BaseModel):
    reason: str
    total_minutes: int
    incident_count: int


class YieldAnalyticsResponse(BaseModel):
    plant_id: str
    from_date: date
    to_date: date
    total_raw_processed_kg: Decimal
    total_output_kg: Decimal
    total_inert_waste_kg: Decimal
    total_variance_kg: Decimal
    overall_recovery_rate_pct: Decimal
    output_breakdown_by_grade: dict[str, Decimal]


class UtilityEfficiencyResponse(BaseModel):
    plant_id: str
    from_date: date
    to_date: date
    total_electricity_kwh: Decimal
    total_diesel_liters: Decimal
    total_strapping_wire_kg: Decimal
    kwh_per_ton_processed: Decimal
    diesel_liters_per_ton_processed: Decimal
    wire_kg_per_baled_ton: Decimal


class DowntimeSummaryResponse(BaseModel):
    plant_id: str
    from_date: date
    to_date: date
    total_downtime_minutes: int
    operational_uptime_pct: Decimal
    breakdown_by_reason: list[DowntimeMetric]