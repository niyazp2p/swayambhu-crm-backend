import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.services.financial_service import FinancialService
from app.schemas.financials import FinancialSummaryResponse

router = APIRouter()


async def _resolve_plant_context(
    db: AsyncSession, current_user: User, plant_id: uuid.UUID | None
) -> uuid.UUID:
    """
    Resolves the plant context:
    1. If plant_id query param is supplied, prioritize it.
    2. If user is plant-scoped (Plant Manager, Operator), use user's plant_id.
    3. If Super Admin omits plant_id, auto-resolve the primary active plant facility.
    """
    if plant_id:
        return plant_id

    if current_user.role != UserRole.SUPER_ADMIN and current_user.plant_id:
        return current_user.plant_id

    # Super Admin fallback: dynamically select the first active operational facility
    active_plant = await db.scalar(
        select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
    )
    if not active_plant:
        # Fallback to any plant row if none are explicitly flagged active
        active_plant = await db.scalar(select(Plant.id).limit(1))

    if not active_plant:
        raise HTTPException(
            status_code=400,
            detail="No operational plant facility registered in database.",
        )
    return active_plant


@router.get("/summary", response_model=FinancialSummaryResponse)
async def get_plant_financial_summary(
    from_date: Annotated[date, Query(description="Start date (YYYY-MM-DD)")],
    to_date: Annotated[date, Query(description="End date (YYYY-MM-DD)")],
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None, description="Optional override for Super Admin"),
    electricity_rate: Decimal = Query(Decimal("8.50"), ge=0, description="Rate per kWh"),
    diesel_rate: Decimal = Query(Decimal("92.00"), ge=0, description="Rate per Liter"),
    wire_rate: Decimal = Query(Decimal("75.00"), ge=0, description="Rate per kg"),
):
    target_plant = await _resolve_plant_context(db, current_user, plant_id)

    service = FinancialService(db)
    return await service.calculate_plant_pl(
        plant_id=target_plant,
        from_date=from_date,
        to_date=to_date,
        electricity_rate=electricity_rate,
        diesel_rate=diesel_rate,
        wire_rate=wire_rate,
    )