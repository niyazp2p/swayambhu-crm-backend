import uuid
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.services.analytics_service import AnalyticsService
from app.schemas.analytics import (
    YieldAnalyticsResponse,
    UtilityEfficiencyResponse,
    DowntimeSummaryResponse,
)

router = APIRouter()


async def _resolve_plant_id(
    db: AsyncSession, current_user: User, plant_id: uuid.UUID | None
) -> uuid.UUID:
    """Resolves plant ID from query param, user scope, or the active database facility."""
    if current_user.role == UserRole.SUPER_ADMIN:
        if plant_id:
            return plant_id
        # Auto-fallback to the active plant (Haridwar SIS-HRD-01)
        active_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )
        if not active_plant:
            raise HTTPException(
                status_code=400,
                detail="No active plant facility found in database.",
            )
        return active_plant

    if not current_user.plant_id:
        raise HTTPException(status_code=400, detail="User is not assigned to a plant.")
    return current_user.plant_id


@router.get("/yield", response_model=YieldAnalyticsResponse)
async def get_yield_analytics(
    from_date: Annotated[date, Query(...)],
    to_date: Annotated[date, Query(...)],
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = None,
):
    target_plant = await _resolve_plant_id(db, current_user, plant_id)
    service = AnalyticsService(db)
    return await service.get_yield_metrics(target_plant, from_date, to_date)


@router.get("/utilities", response_model=UtilityEfficiencyResponse)
async def get_utility_analytics(
    from_date: Annotated[date, Query(...)],
    to_date: Annotated[date, Query(...)],
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = None,
):
    target_plant = await _resolve_plant_id(db, current_user, plant_id)
    service = AnalyticsService(db)
    return await service.get_utility_metrics(target_plant, from_date, to_date)


@router.get("/downtime", response_model=DowntimeSummaryResponse)
async def get_downtime_analytics(
    from_date: Annotated[date, Query(...)],
    to_date: Annotated[date, Query(...)],
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = None,
):
    target_plant = await _resolve_plant_id(db, current_user, plant_id)
    service = AnalyticsService(db)
    return await service.get_downtime_metrics(target_plant, from_date, to_date)