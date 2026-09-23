import uuid
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict


class FinancialSummaryRequest(BaseModel):
    from_date: date
    to_date: date
    electricity_unit_rate: Decimal = Field(
        default=Decimal("8.50"), ge=0, description="Cost per kWh"
    )
    diesel_unit_rate: Decimal = Field(
        default=Decimal("92.00"), ge=0, description="Cost per Liter"
    )
    strapping_wire_unit_rate: Decimal = Field(
        default=Decimal("75.00"), ge=0, description="Cost per kg"
    )


class ExpenseBreakdown(BaseModel):
    raw_material_cogs: Decimal
    payroll_wages: Decimal
    electricity_cost: Decimal
    diesel_cost: Decimal
    strapping_wire_cost: Decimal
    total_operating_expenses: Decimal

    model_config = ConfigDict(from_attributes=True)


class FinancialSummaryResponse(BaseModel):
    plant_id: uuid.UUID
    from_date: date
    to_date: date
    total_tonnage_processed_mt: Decimal
    total_sales_revenue: Decimal
    expenses: ExpenseBreakdown
    gross_operating_margin: Decimal
    net_operating_ebitda: Decimal
    ebitda_margin_pct: Decimal
    ebitda_per_processed_ton: Decimal

    model_config = ConfigDict(from_attributes=True)