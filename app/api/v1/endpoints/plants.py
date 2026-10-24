import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict

from app.db.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User, UserRole
from app.models.plant import Plant

router = APIRouter()


class PlantResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


@router.get("", response_model=list[PlantResponse])
async def list_plants(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    List all active operational recycling facilities.
    Super Admins see all active plants; Plant-scoped users see their assigned facility.
    """
    stmt = select(Plant).where(Plant.is_active.is_(True)).order_by(Plant.created_at.asc())
    
    if current_user.role != UserRole.SUPER_ADMIN and current_user.plant_id:
        stmt = stmt.where(Plant.id == current_user.plant_id)

    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{plant_id}", response_model=PlantResponse)
async def get_plant_by_id(
    plant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    plant = await db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant facility not found.",
        )
    return plant