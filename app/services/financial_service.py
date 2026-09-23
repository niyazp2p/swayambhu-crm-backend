import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import select, func, and_, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.procurement import GRNRecord
from app.models.hr import Payslip
from app.models.operations import DailyProgressReport
from app.models.sales import DispatchOrder
from app.schemas.financials import (
    ExpenseBreakdown,
    FinancialSummaryResponse,
)


class FinancialService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def calculate_plant_pl(
        self,
        plant_id: uuid.UUID,
        from_date: date,
        to_date: date,
        electricity_rate: Decimal,
        diesel_rate: Decimal,
        wire_rate: Decimal,
    ) -> FinancialSummaryResponse:
        # ---------------------------------------------------------------------
        # 1. Total Sales Revenue from Outward Dispatches
        # ---------------------------------------------------------------------
        sales_stmt = (
            select(func.coalesce(func.sum(DispatchOrder.total_amount), Decimal("0.00")))
            .select_from(DispatchOrder)
            .where(
                and_(
                    DispatchOrder.plant_id == plant_id,
                    DispatchOrder.dispatch_date >= from_date,
                    DispatchOrder.dispatch_date <= to_date,
                )
            )
        )
        sales_raw = (await self.db.execute(sales_stmt)).scalar()
        total_sales_revenue = Decimal(str(sales_raw)) if sales_raw is not None else Decimal("0.00")

        # ---------------------------------------------------------------------
        # 2. Raw Material Feedstock COGS (Directly sum stored intake payable)
        # Using cast(Date) to avoid timezone-offset crashes on created_at
        # ---------------------------------------------------------------------
        cogs_stmt = (
            select(func.coalesce(func.sum(GRNRecord.total_payable_amount), Decimal("0.00")))
            .select_from(GRNRecord)
            .where(
                and_(
                    GRNRecord.plant_id == plant_id,
                    cast(GRNRecord.created_at, Date) >= from_date,
                    cast(GRNRecord.created_at, Date) <= to_date,
                )
            )
        )
        cogs_raw = (await self.db.execute(cogs_stmt)).scalar()
        raw_material_cogs = Decimal(str(cogs_raw)) if cogs_raw is not None else Decimal("0.00")

        # ---------------------------------------------------------------------
        # 3. Monthly Disbursed Payroll Wages
        # ---------------------------------------------------------------------
        payroll_stmt = (
            select(func.coalesce(func.sum(Payslip.net_salary), Decimal("0.00")))
            .select_from(Payslip)
            .where(
                and_(
                    Payslip.plant_id == plant_id,
                    Payslip.year >= from_date.year,
                    Payslip.year <= to_date.year,
                    Payslip.month >= from_date.month,
                    Payslip.month <= to_date.month,
                )
            )
        )
        payroll_raw = (await self.db.execute(payroll_stmt)).scalar()
        payroll_wages = Decimal(str(payroll_raw)) if payroll_raw is not None else Decimal("0.00")

        # ---------------------------------------------------------------------
        # 4. Utilities and Raw Processed Tonnage from DPR
        # ---------------------------------------------------------------------
        dpr_stmt = (
            select(
                func.coalesce(func.sum(DailyProgressReport.total_raw_processed_kg), Decimal("0.00")),
                func.coalesce(func.sum(DailyProgressReport.electricity_kwh), Decimal("0.00")),
                func.coalesce(func.sum(DailyProgressReport.diesel_liters), Decimal("0.00")),
                func.coalesce(func.sum(DailyProgressReport.strapping_wire_kg), Decimal("0.00")),
            )
            .select_from(DailyProgressReport)
            .where(
                and_(
                    DailyProgressReport.plant_id == plant_id,
                    DailyProgressReport.report_date >= from_date,
                    DailyProgressReport.report_date <= to_date,
                )
            )
        )
        row = (await self.db.execute(dpr_stmt)).one()
        raw_kg = Decimal(str(row[0])) if row[0] is not None else Decimal("0.00")
        kwh = Decimal(str(row[1])) if row[1] is not None else Decimal("0.00")
        diesel = Decimal(str(row[2])) if row[2] is not None else Decimal("0.00")
        wire = Decimal(str(row[3])) if row[3] is not None else Decimal("0.00")

        total_tonnage_processed_mt = round(raw_kg / Decimal("1000.00"), 2)
        electricity_cost = round(kwh * electricity_rate, 2)
        diesel_cost = round(diesel * diesel_rate, 2)
        wire_cost = round(wire * wire_rate, 2)

        # ---------------------------------------------------------------------
        # 5. Financial Aggregations & Margins
        # ---------------------------------------------------------------------
        total_opex = raw_material_cogs + payroll_wages + electricity_cost + diesel_cost + wire_cost
        gross_margin = total_sales_revenue - raw_material_cogs
        net_ebitda = total_sales_revenue - total_opex

        ebitda_margin_pct = Decimal("0.00")
        if total_sales_revenue > 0:
            ebitda_margin_pct = round((net_ebitda / total_sales_revenue) * Decimal("100.00"), 2)

        ebitda_per_ton = Decimal("0.00")
        if total_tonnage_processed_mt > 0:
            ebitda_per_ton = round(net_ebitda / total_tonnage_processed_mt, 2)

        return FinancialSummaryResponse(
            plant_id=plant_id,
            from_date=from_date,
            to_date=to_date,
            total_tonnage_processed_mt=total_tonnage_processed_mt,
            total_sales_revenue=round(total_sales_revenue, 2),
            expenses=ExpenseBreakdown(
                raw_material_cogs=round(raw_material_cogs, 2),
                payroll_wages=round(payroll_wages, 2),
                electricity_cost=electricity_cost,
                diesel_cost=diesel_cost,
                strapping_wire_cost=wire_cost,
                total_operating_expenses=round(total_opex, 2),
            ),
            gross_operating_margin=round(gross_margin, 2),
            net_operating_ebitda=round(net_ebitda, 2),
            ebitda_margin_pct=ebitda_margin_pct,
            ebitda_per_processed_ton=ebitda_per_ton,
        )