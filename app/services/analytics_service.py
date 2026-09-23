import uuid
from datetime import date
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.operations import DailyProgressReport, ProductionLog, DowntimeLog
from app.models.procurement import WasteGrade
from app.schemas.analytics import (
    YieldAnalyticsResponse,
    UtilityEfficiencyResponse,
    DowntimeSummaryResponse,
    DowntimeMetric,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_yield_metrics(
        self, plant_id: uuid.UUID, from_date: date, to_date: date
    ) -> YieldAnalyticsResponse:
        # Aggregate totals across Daily Progress Reports
        stmt = (
            select(
                func.coalesce(func.sum(DailyProgressReport.total_raw_processed_kg), 0),
                func.coalesce(func.sum(DailyProgressReport.total_output_produced_kg), 0),
                func.coalesce(func.sum(DailyProgressReport.total_inert_waste_kg), 0),
                func.coalesce(func.sum(DailyProgressReport.mass_balance_variance_kg), 0),
            )
            .where(DailyProgressReport.plant_id == plant_id)
            .where(DailyProgressReport.report_date >= from_date)
            .where(DailyProgressReport.report_date <= to_date)
        )
        res = await self.db.execute(stmt)
        raw_proc, out_proc, inert, variance = res.one()

        raw_proc = Decimal(str(raw_proc))
        out_proc = Decimal(str(out_proc))
        inert = Decimal(str(inert))
        variance = Decimal(str(variance))

        recovery_rate = Decimal("0.00")
        if raw_proc > 0:
            recovery_rate = round((out_proc / raw_proc) * Decimal("100.00"), 2)

        # Aggregate output by waste grade
        grade_stmt = (
            select(WasteGrade.grade_code, func.coalesce(func.sum(ProductionLog.output_weight_kg), 0))
            .join(DailyProgressReport, ProductionLog.dpr_id == DailyProgressReport.id)
            .join(WasteGrade, ProductionLog.waste_grade_id == WasteGrade.id)
            .where(DailyProgressReport.plant_id == plant_id)
            .where(DailyProgressReport.report_date >= from_date)
            .where(DailyProgressReport.report_date <= to_date)
            .group_by(WasteGrade.grade_code)
        )
        grade_res = await self.db.execute(grade_stmt)
        breakdown = {row[0]: Decimal(str(row[1])) for row in grade_res.all()}

        return YieldAnalyticsResponse(
            plant_id=str(plant_id),
            from_date=from_date,
            to_date=to_date,
            total_raw_processed_kg=raw_proc,
            total_output_kg=out_proc,
            total_inert_waste_kg=inert,
            total_variance_kg=variance,
            overall_recovery_rate_pct=recovery_rate,
            output_breakdown_by_grade=breakdown,
        )

    async def get_utility_metrics(
        self, plant_id: uuid.UUID, from_date: date, to_date: date
    ) -> UtilityEfficiencyResponse:
        stmt = (
            select(
                func.coalesce(func.sum(DailyProgressReport.electricity_kwh), 0),
                func.coalesce(func.sum(DailyProgressReport.diesel_liters), 0),
                func.coalesce(func.sum(DailyProgressReport.strapping_wire_kg), 0),
                func.coalesce(func.sum(DailyProgressReport.total_raw_processed_kg), 0),
                func.coalesce(func.sum(DailyProgressReport.total_output_produced_kg), 0),
            )
            .where(DailyProgressReport.plant_id == plant_id)
            .where(DailyProgressReport.report_date >= from_date)
            .where(DailyProgressReport.report_date <= to_date)
        )
        res = await self.db.execute(stmt)
        kwh, diesel, wire, raw_kg, out_kg = res.one()

        kwh = Decimal(str(kwh))
        diesel = Decimal(str(diesel))
        wire = Decimal(str(wire))
        processed_tons = Decimal(str(raw_kg)) / Decimal("1000.00")
        baled_tons = Decimal(str(out_kg)) / Decimal("1000.00")

        kwh_per_ton = round(kwh / processed_tons, 2) if processed_tons > 0 else Decimal("0.00")
        diesel_per_ton = round(diesel / processed_tons, 2) if processed_tons > 0 else Decimal("0.00")
        wire_per_baled_ton = round(wire / baled_tons, 2) if baled_tons > 0 else Decimal("0.00")

        return UtilityEfficiencyResponse(
            plant_id=str(plant_id),
            from_date=from_date,
            to_date=to_date,
            total_electricity_kwh=kwh,
            total_diesel_liters=diesel,
            total_strapping_wire_kg=wire,
            kwh_per_ton_processed=kwh_per_ton,
            diesel_liters_per_ton_processed=diesel_per_ton,
            wire_kg_per_baled_ton=wire_per_baled_ton,
        )

    async def get_downtime_metrics(
        self, plant_id: uuid.UUID, from_date: date, to_date: date
    ) -> DowntimeSummaryResponse:
        days_in_period = max((to_date - from_date).days + 1, 1)
        total_scheduled_minutes = days_in_period * 24 * 60

        stmt = (
            select(
                DowntimeLog.reason,
                func.coalesce(func.sum(DowntimeLog.duration_minutes), 0),
                func.count(DowntimeLog.id),
            )
            .join(DailyProgressReport, DowntimeLog.dpr_id == DailyProgressReport.id)
            .where(DailyProgressReport.plant_id == plant_id)
            .where(DailyProgressReport.report_date >= from_date)
            .where(DailyProgressReport.report_date <= to_date)
            .group_by(DowntimeLog.reason)
        )
        res = await self.db.execute(stmt)
        rows = res.all()

        breakdown = [
            DowntimeMetric(
                reason=row[0].value if hasattr(row[0], "value") else str(row[0]),
                total_minutes=int(row[1]),
                incident_count=int(row[2]),
            )
            for row in rows
        ]

        total_downtime = sum(m.total_minutes for m in breakdown)
        uptime_minutes = max(total_scheduled_minutes - total_downtime, 0)
        uptime_pct = round(
            (Decimal(uptime_minutes) / Decimal(total_scheduled_minutes)) * Decimal("100.00"), 2
        )

        return DowntimeSummaryResponse(
            plant_id=str(plant_id),
            from_date=from_date,
            to_date=to_date,
            total_downtime_minutes=total_downtime,
            operational_uptime_pct=uptime_pct,
            breakdown_by_reason=breakdown,
        )