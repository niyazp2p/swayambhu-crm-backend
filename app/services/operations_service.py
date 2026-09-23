import uuid
from datetime import date
from decimal import Decimal
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.operations import (
    DailyProgressReport,
    ProductionLog,
    DowntimeLog,
    DowntimeReason,
)
from app.models.inventory import FinishedGoodsInventory
from app.schemas.operations import DPRCreate, DPRUpdate, DowntimeLogStandaloneCreate


class OperationsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_dpr(
        self, plant_id: uuid.UUID, supervisor_id: uuid.UUID, payload: DPRCreate
    ) -> DailyProgressReport:
        # Check duplicate submission for date
        existing = await self.db.scalar(
            select(DailyProgressReport.id).where(
                DailyProgressReport.plant_id == plant_id,
                DailyProgressReport.report_date == payload.report_date,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A Daily Progress Report for plant {plant_id} on {payload.report_date} already exists.",
            )

        # 1. Compute production yield & mass balance variance
        total_output = sum(
            (item.output_weight_kg for item in payload.production_items),
            Decimal("0.00"),
        )
        variance = payload.total_raw_processed_kg - (
            total_output + payload.total_inert_waste_kg
        )

        # 2. Instantiate Master DPR
        dpr = DailyProgressReport(
            plant_id=plant_id,
            report_date=payload.report_date,
            supervisor_id=supervisor_id,
            electricity_kwh=payload.electricity_kwh,
            diesel_liters=payload.diesel_liters,
            strapping_wire_kg=payload.strapping_wire_kg,
            total_raw_processed_kg=payload.total_raw_processed_kg,
            total_output_produced_kg=total_output,
            total_inert_waste_kg=payload.total_inert_waste_kg,
            mass_balance_variance_kg=variance,
            remarks=payload.remarks,
        )
        self.db.add(dpr)
        await self.db.flush()

        # 3. Insert Production Logs and update Finished Goods Stock
        for item in payload.production_items:
            prod_log = ProductionLog(
                dpr_id=dpr.id,
                waste_grade_id=item.waste_grade_id,
                output_weight_kg=item.output_weight_kg,
                bales_produced=item.bales_produced,
            )
            self.db.add(prod_log)

            # Atomically lock ONLY the inventory table (prevents outer join lock error)
            inv_stmt = (
                select(FinishedGoodsInventory)
                .where(
                    FinishedGoodsInventory.plant_id == plant_id,
                    FinishedGoodsInventory.waste_grade_id == item.waste_grade_id,
                )
                .with_for_update(of=FinishedGoodsInventory)
            )
            inv_res = await self.db.execute(inv_stmt)
            stock_record = inv_res.scalar_one_or_none()

            if stock_record:
                stock_record.current_stock_kg += item.output_weight_kg
                stock_record.bales_in_stock += item.bales_produced
            else:
                self.db.add(
                    FinishedGoodsInventory(
                        plant_id=plant_id,
                        waste_grade_id=item.waste_grade_id,
                        current_stock_kg=item.output_weight_kg,
                        bales_in_stock=item.bales_produced,
                    )
                )

        # 4. Insert Downtime logs attached to this DPR
        for dt in payload.downtime_logs:
            self.db.add(
                DowntimeLog(
                    plant_id=plant_id,
                    dpr_id=dpr.id,
                    reason=dt.reason,
                    duration_minutes=dt.duration_minutes,
                    equipment_name=dt.equipment_name,
                    description=dt.description,
                )
            )

        await self.db.commit()
        return await self.get_dpr_by_id(dpr.id, plant_id=None)

    async def get_dpr_by_id(
        self, dpr_id: uuid.UUID, plant_id: uuid.UUID | None = None
    ) -> DailyProgressReport:
        query = (
            select(DailyProgressReport)
            .options(
                selectinload(DailyProgressReport.production_items),
                selectinload(DailyProgressReport.downtime_logs),
            )
            .where(DailyProgressReport.id == dpr_id)
        )
        if plant_id:
            query = query.where(DailyProgressReport.plant_id == plant_id)

        res = await self.db.execute(query)
        dpr = res.scalar_one_or_none()
        if not dpr:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Daily Progress Report not found.",
            )
        return dpr

    async def list_dprs(
        self,
        plant_id: uuid.UUID | None,
        from_date: date | None = None,
        to_date: date | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DailyProgressReport]:
        query = (
            select(DailyProgressReport)
            .options(
                selectinload(DailyProgressReport.production_items),
                selectinload(DailyProgressReport.downtime_logs),
            )
            .order_by(DailyProgressReport.report_date.desc())
        )
        if plant_id:
            query = query.where(DailyProgressReport.plant_id == plant_id)
        if from_date:
            query = query.where(DailyProgressReport.report_date >= from_date)
        if to_date:
            query = query.where(DailyProgressReport.report_date <= to_date)

        res = await self.db.execute(query.limit(limit).offset(offset))
        return list(res.scalars().all())

    async def create_standalone_downtime(
        self, plant_id: uuid.UUID, payload: DowntimeLogStandaloneCreate
    ) -> DowntimeLog:
        downtime = DowntimeLog(
            plant_id=plant_id,
            reason=payload.reason,
            duration_minutes=payload.duration_minutes,
            equipment_name=payload.equipment_name,
            description=payload.description,
        )
        self.db.add(downtime)
        await self.db.commit()
        await self.db.refresh(downtime)
        return downtime

    async def list_downtimes(
        self,
        plant_id: uuid.UUID | None,
        reason: DowntimeReason | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DowntimeLog]:
        query = select(DowntimeLog).order_by(DowntimeLog.created_at.desc())
        if plant_id:
            query = query.where(DowntimeLog.plant_id == plant_id)
        if reason:
            query = query.where(DowntimeLog.reason == reason)

        res = await self.db.execute(query.limit(limit).offset(offset))
        return list(res.scalars().all())