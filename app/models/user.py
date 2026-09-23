import enum
import uuid
from sqlalchemy import String, Boolean, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"
    PLANT_MANAGER = "PLANT_MANAGER"
    WEIGHBRIDGE_OPERATOR = "WEIGHBRIDGE_OPERATOR"
    HR_OFFICER = "HR_OFFICER"
    SALES_LOGISTICS = "SALES_LOGISTICS"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"), nullable=False, default=UserRole.WEIGHBRIDGE_OPERATOR
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Plant Scoping (NULL for SUPER_ADMIN, required for other roles)
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Relationships
    plant: Mapped["Plant | None"] = relationship("Plant", back_populates="users")