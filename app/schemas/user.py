import uuid
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict, field_validator
from app.models.user import UserRole


class PlantReference(BaseModel):
    id: uuid.UUID
    name: str
    code: str

    model_config = ConfigDict(from_attributes=True)


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole = Field(default=UserRole.WEIGHBRIDGE_OPERATOR)
    plant_id: uuid.UUID | None = None
    is_active: bool = True


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=100)
    role: UserRole
    plant_id: uuid.UUID | None = None

    @field_validator("plant_id")
    @classmethod
    def validate_plant_scoping(cls, v: uuid.UUID | None, info) -> uuid.UUID | None:
        role = info.data.get("role")
        if role == UserRole.SUPER_ADMIN:
            return None  # Super Admins operate globally with NULL plant_id
        if role and role != UserRole.SUPER_ADMIN and v is None:
            raise ValueError(f"Operational role '{role}' must be bound to a designated plant_id.")
        return v


class UserUpdate(BaseModel):
    full_name: str | None = Field(None, min_length=2, max_length=100)
    role: UserRole | None = None
    plant_id: uuid.UUID | None = None
    is_active: bool | None = None


class UserPasswordReset(BaseModel):
    new_password: str = Field(..., min_length=8, max_length=128)


class UserStatusToggle(BaseModel):
    is_active: bool


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    plant_id: uuid.UUID | None
    plant: PlantReference | None = None
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)