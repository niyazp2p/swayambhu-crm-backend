import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    Resolves the facility context:
    1. If user is Super Admin and provides plant_id, use it.
    2. If user is Super Admin and omits plant_id, dynamically fallback to the active plant.
    3. If user is plant-scoped (Plant Manager, Operator), enforce their assigned plant_id.
    """
    if current_user.role == UserRole.SUPER_ADMIN:
        if plant_id:
            return plant_id

        # Fallback to the active facility
        active_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )
        if not active_plant:
            active_plant = await db.scalar(select(Plant.id).limit(1))

        if not active_plant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Plant context required. No active plant registered in the database.",
            )
        return active_plant

    # Non-super-admin user validation
    if not current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not assigned to a plant facility.",
        )

    if plant_id and plant_id != current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Cannot query financial records for an unassigned facility.",
        )

    return current_user.plant_id


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
    electricity_rate: Decimal = Query(
        Decimal("8.50"), ge=0, alias="electricity_rate", description="Rate per kWh"
    ),
    diesel_rate: Decimal = Query(
        Decimal("92.00"), ge=0, alias="diesel_rate", description="Rate per Liter"
    ),
    wire_rate: Decimal = Query(
        Decimal("75.00"), ge=0, alias="wire_rate", description="Rate per kg"
    ),
):
    if from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date range: 'from_date' cannot be later than 'to_date'.",
        )

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