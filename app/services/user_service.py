import uuid
from sqlalchemy import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.schemas.user import UserCreate, UserUpdate
from app.core.security import get_password_hash


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_users(
        self,
        role: UserRole | None = None,
        plant_id: uuid.UUID | None = None,
        is_active: bool | None = None,
    ) -> list[User]:
        query = select(User).options(joinedload(User.plant)).order_by(User.full_name.asc())

        if role is not None:
            query = query.where(User.role == role)
        if plant_id is not None:
            query = query.where(User.plant_id == plant_id)
        if is_active is not None:
            query = query.where(User.is_active == is_active)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        query = select(User).options(joinedload(User.plant)).where(User.id == user_id)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User account '{user_id}' not found.",
            )
        return user

    async def create_user(self, payload: UserCreate) -> User:
        # 1. Unique email constraint
        existing = await self.db.scalar(select(User.id).where(User.email == payload.email.lower()))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email address already exists.",
            )

        # 2. Plant existence verification for plant-scoped roles
        target_plant_id = None
        if payload.role != UserRole.SUPER_ADMIN:
            if not payload.plant_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Plant assignment is mandatory for role '{payload.role}'.",
                )
            plant_exists = await self.db.scalar(select(Plant.id).where(Plant.id == payload.plant_id))
            if not plant_exists:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assigned plant facility does not exist.",
                )
            target_plant_id = payload.plant_id

        # 3. Create user record
        user = User(
            email=payload.email.lower().strip(),
            hashed_password=get_password_hash(payload.password),
            full_name=payload.full_name.strip(),
            role=payload.role,
            plant_id=target_plant_id,
            is_active=True,
        )
        self.db.add(user)
        await self.db.commit()
        return await self.get_by_id(user.id)

    async def update_user(self, user_id: uuid.UUID, payload: UserUpdate, actor_id: uuid.UUID) -> User:
        user = await self.get_by_id(user_id)

        if payload.full_name is not None:
            user.full_name = payload.full_name.strip()

        # Update Role & Scope
        target_role = payload.role if payload.role is not None else user.role
        if target_role == UserRole.SUPER_ADMIN:
            user.role = UserRole.SUPER_ADMIN
            user.plant_id = None
        else:
            if payload.plant_id is not None:
                plant_exists = await self.db.scalar(select(Plant.id).where(Plant.id == payload.plant_id))
                if not plant_exists:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specified plant does not exist.")
                user.plant_id = payload.plant_id
            elif user.plant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Assigning role '{target_role}' requires a valid plant_id.",
                )
            user.role = target_role

        # Self-deactivation prevention
        if payload.is_active is not None:
            if user.id == actor_id and not payload.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You cannot deactivate your own administrative account.",
                )
            user.is_active = payload.is_active

        await self.db.commit()
        return await self.get_by_id(user.id)

    async def toggle_status(self, user_id: uuid.UUID, is_active: bool, actor_id: uuid.UUID) -> User:
        if user_id == actor_id and not is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security lockout protection: You cannot disable your own active account.",
            )
        user = await self.get_by_id(user_id)
        user.is_active = is_active
        await self.db.commit()
        return await self.get_by_id(user.id)

    async def reset_password(self, user_id: uuid.UUID, new_password: str) -> None:
        user = await self.get_by_id(user_id)
        user.hashed_password = get_password_hash(new_password)
        await self.db.commit()

    async def delete_user(self, user_id: uuid.UUID, actor_id: uuid.UUID) -> dict[str, str]:
        if user_id == actor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Security lockout protection: You cannot delete your own account.",
            )
        user = await self.get_by_id(user_id)

        try:
            # 1. Attempt permanent removal from the database
            await self.db.delete(user)
            await self.db.commit()
            return {
                "message": f"User '{user.email}' has been permanently purged.",
                "action": "DELETED",
                "user_id": str(user_id),
            }
        except IntegrityError:
            # 2. Foreign Key violation fallback: account is tied to historical audit logs (e.g. grn_records)
            await self.db.rollback()

            # Re-fetch user in rolled back session and soft-deactivate
            user = await self.get_by_id(user_id)
            user.is_active = False
            await self.db.commit()

            return {
                "message": f"User '{user.email}' is linked to inward GRN/dispatch records. Account access has been revoked and deactivated to preserve audit compliance.",
                "action": "DEACTIVATED",
                "user_id": str(user_id),
            }