import enum
import uuid
from datetime import date, time
from decimal import Decimal
from sqlalchemy import (
    String,
    Numeric,
    Boolean,
    Enum,
    ForeignKey,
    Date,
    Time,
    Integer,
    UniqueConstraint,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class EmployeeRole(str, enum.Enum):
    SORTER = "SORTER"
    OPERATOR = "OPERATOR"
    DRIVER = "DRIVER"
    ADMIN = "ADMIN"
    SUPERVISOR = "SUPERVISOR"


class WageType(str, enum.Enum):
    DAILY_WAGE = "DAILY_WAGE"
    MONTHLY_FIXED = "MONTHLY_FIXED"


class AttendanceStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    HALF_DAY = "HALF_DAY"
    ON_LEAVE = "ON_LEAVE"


class AdvanceStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    REPAID = "REPAID"


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employee_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[EmployeeRole] = mapped_column(
        Enum(EmployeeRole, name="employee_role_enum"), nullable=False, index=True
    )
    wage_type: Mapped[WageType] = mapped_column(
        Enum(WageType, name="wage_type_enum"), nullable=False
    )
    base_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)  # Daily wage or monthly fixed salary
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bank_account_no: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant", foreign_keys=[plant_id])
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="employee", cascade="all, delete-orphan"
    )
    advances: Mapped[list["SalaryAdvance"]] = relationship(
        "SalaryAdvance", back_populates="employee", cascade="all, delete-orphan"
    )
    payslips: Mapped[list["Payslip"]] = relationship(
        "Payslip", back_populates="employee", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_employees_plant_active", "plant_id", "is_active"),
    )


class AttendanceRecord(Base, TimestampMixin):
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(AttendanceStatus, name="attendance_status_enum"), default=AttendanceStatus.PRESENT, nullable=False
    )
    check_in: Mapped[time | None] = mapped_column(Time, nullable=True)
    check_out: Mapped[time | None] = mapped_column(Time, nullable=True)
    is_late: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("0.00"), nullable=False)

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant", foreign_keys=[plant_id])
    employee: Mapped["Employee"] = relationship("Employee", back_populates="attendance_records")

    __table_args__ = (
        # Ensures one attendance punch record per employee per day
        UniqueConstraint("employee_id", "attendance_date", name="uq_employee_attendance_date"),
        Index("ix_attendance_plant_date", "plant_id", "attendance_date"),
    )


class SalaryAdvance(Base, TimestampMixin):
    __tablename__ = "salary_advances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    tenure_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_emi: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    remaining_balance: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[AdvanceStatus] = mapped_column(
        Enum(AdvanceStatus, name="advance_status_enum"), default=AdvanceStatus.ACTIVE, nullable=False, index=True
    )

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant", foreign_keys=[plant_id])
    employee: Mapped["Employee"] = relationship("Employee", back_populates="advances")

    __table_args__ = (
        Index("ix_advances_employee_status", "employee_id", "status"),
    )


class Payslip(Base, TimestampMixin):
    __tablename__ = "payslips"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Earnings
    gross_earnings: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    overtime_earnings: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)

    # Itemized Deductions
    absence_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    late_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    advance_emi_deduction: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Final Payout
    net_salary: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant", foreign_keys=[plant_id])
    employee: Mapped["Employee"] = relationship("Employee", back_populates="payslips")

    __table_args__ = (
        # Prevents duplicate payslips for the same employee in the same payroll period
        UniqueConstraint("employee_id", "month", "year", name="uq_employee_monthly_payslip"),
        Index("ix_payslips_plant_period", "plant_id", "year", "month"),
    )