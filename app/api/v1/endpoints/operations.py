import uuid
from datetime import date
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.models.operations import DowntimeReason
from app.schemas.operations import (
    DPRCreate,
    DPRResponse,
    DowntimeLogResponse,
    DowntimeLogStandaloneCreate,
)
from app.services.operations_service import OperationsService

router = APIRouter()


async def _resolve_plant_context(
    db: AsyncSession, current_user: User, explicit_plant_id: uuid.UUID | None = None
) -> uuid.UUID:
    """
    Resolves the plant context:
    1. Explicit query or payload plant_id.
    2. Assigned plant_id for plant-scoped roles (Plant Manager, Operator).
    3. Auto-fallback to active operational facility for Super Admin.
    """
    target_plant = explicit_plant_id or current_user.plant_id

    # Auto-resolve active facility for Super Admin if unassigned
    if not target_plant and current_user.role == UserRole.SUPER_ADMIN:
        target_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )
        if not target_plant:
            target_plant = await db.scalar(select(Plant.id).limit(1))

    if not target_plant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plant context required. No active plant registered in the database.",
        )

    if current_user.role != UserRole.SUPER_ADMIN and current_user.plant_id != target_plant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Cannot operate on non-assigned plant.",
        )

    return target_plant


# =====================================================================
# 1. DAILY PROGRESS REPORTS (DPR)
# =====================================================================

@router.post("/dpr", response_model=DPRResponse, status_code=status.HTTP_201_CREATED)
async def submit_daily_progress_report(
    dpr_in: DPRCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
):
    target_plant = await _resolve_plant_context(
        db, current_user, explicit_plant_id=plant_id or getattr(dpr_in, "plant_id", None)
    )
    service = OperationsService(db)
    return await service.create_dpr(
        plant_id=target_plant, supervisor_id=current_user.id, payload=dpr_in
    )


@router.get("/dpr", response_model=list[DPRResponse])
async def list_daily_progress_reports(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    target_plant = plant_id if current_user.role == UserRole.SUPER_ADMIN else current_user.plant_id
    service = OperationsService(db)
    return await service.list_dprs(
        plant_id=target_plant,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )


@router.get("/dpr/{dpr_id}", response_model=DPRResponse)
async def get_dpr_by_id(
    dpr_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    plant_id = None if current_user.role == UserRole.SUPER_ADMIN else current_user.plant_id
    service = OperationsService(db)
    return await service.get_dpr_by_id(dpr_id=dpr_id, plant_id=plant_id)


# =====================================================================
# 2. MACHINE DOWNTIME TRACKING
# =====================================================================

@router.post("/downtime", response_model=DowntimeLogResponse, status_code=status.HTTP_201_CREATED)
async def log_standalone_downtime(
    downtime_in: DowntimeLogStandaloneCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
):
    target_plant = await _resolve_plant_context(
        db, current_user, explicit_plant_id=plant_id or getattr(downtime_in, "plant_id", None)
    )
    service = OperationsService(db)
    return await service.create_standalone_downtime(plant_id=target_plant, payload=downtime_in)


@router.get("/downtime", response_model=list[DowntimeLogResponse])
async def list_downtime_records(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
    reason: DowntimeReason | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    target_plant = plant_id if current_user.role == UserRole.SUPER_ADMIN else current_user.plant_id
    service = OperationsService(db)
    return await service.list_downtimes(
        plant_id=target_plant, reason=reason, limit=limit, offset=offset
    )