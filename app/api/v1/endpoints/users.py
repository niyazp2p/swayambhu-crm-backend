import uuid
from typing import Annotated
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserPasswordReset,
    UserStatusToggle,
)
from app.services.user_service import UserService
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: UserRole | None = Query(None, description="Filter by RBAC clearance"),
    plant_id: uuid.UUID | None = Query(None, description="Filter by facility node"),
    is_active: bool | None = Query(None, description="Filter by active status"),
):
    """Retrieve operational user accounts across all facilities (Super Admin exclusive)[cite: 1]."""
    service = UserService(db)
    return await service.list_users(role=role, plant_id=plant_id, is_active=is_active)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Provision a new login account with assigned RBAC clearance and plant scoping."""
    service = UserService(db)
    return await service.create_user(payload)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_detail(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Inspect user profile, roles, and assigned facility node[cite: 1]."""
    service = UserService(db)
    return await service.get_by_id(user_id)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update profile attributes, RBAC role, plant reassignment, or active state[cite: 1]."""
    service = UserService(db)
    return await service.update_user(user_id=user_id, payload=payload, actor_id=current_user.id)


@router.patch("/{user_id}/status", response_model=UserResponse)
async def toggle_user_status(
    user_id: uuid.UUID,
    payload: UserStatusToggle,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Enable or disable operational access without deleting audit logs[cite: 1, 3]."""
    service = UserService(db)
    return await service.toggle_status(user_id=user_id, is_active=payload.is_active, actor_id=current_user.id)


@router.post("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: UserPasswordReset,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Set new password credentials for an existing account[cite: 1, 3]."""
    service = UserService(db)
    await service.reset_password(user_id=user_id, new_password=payload.new_password)
    return {"message": "Password reset successfully completed."}


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: uuid.UUID,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Soft-deactivates the user to preserve weighbridge, payroll, and stock ledger history[cite: 1, 3]."""
    service = UserService(db)
    return await service.delete_user(user_id=user_id, actor_id=current_user.id)