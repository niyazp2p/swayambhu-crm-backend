import uuid
from decimal import Decimal
from datetime import date, time, datetime
from pydantic import BaseModel, Field, ConfigDict
from app.models.hr import EmployeeRole, WageType, AttendanceStatus, AdvanceStatus


# --- 1. Employees ---
class EmployeeCreate(BaseModel):
    employee_code: str
    full_name: str
    role: EmployeeRole
    wage_type: WageType
    base_rate: Decimal = Field(..., gt=0)
    phone: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None


class EmployeeUpdate(BaseModel):
    full_name: str | None = None
    role: EmployeeRole | None = None
    wage_type: WageType | None = None
    base_rate: Decimal | None = Field(None, gt=0)
    phone: str | None = None
    bank_account_no: str | None = None
    bank_ifsc: str | None = None
    is_active: bool | None = None


class EmployeeResponse(EmployeeCreate):
    id: uuid.UUID
    plant_id: uuid.UUID
    is_active: bool
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- 2. Attendance ---
class AttendanceCreate(BaseModel):
    employee_id: uuid.UUID
    attendance_date: date
    status: AttendanceStatus = AttendanceStatus.PRESENT
    check_in: time | None = None
    check_out: time | None = None
    is_late: bool = False
    overtime_hours: Decimal = Field(default=Decimal("0.00"), ge=0)


class AttendanceBulkCreate(BaseModel):
    records: list[AttendanceCreate]


class AttendanceUpdate(BaseModel):
    status: AttendanceStatus | None = None
    check_in: time | None = None
    check_out: time | None = None
    is_late: bool | None = None
    overtime_hours: Decimal | None = Field(None, ge=0)


class AttendanceResponse(AttendanceCreate):
    id: uuid.UUID
    plant_id: uuid.UUID
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- 3. Salary Advances ---
class AdvanceCreate(BaseModel):
    employee_id: uuid.UUID
    principal_amount: Decimal = Field(..., gt=0)
    tenure_months: int = Field(..., gt=0)


class AdvanceSettlement(BaseModel):
    settlement_amount: Decimal = Field(..., gt=0)


class AdvanceResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    employee_id: uuid.UUID
    principal_amount: Decimal
    tenure_months: int
    monthly_emi: Decimal
    remaining_balance: Decimal
    status: AdvanceStatus
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# --- 4. Payroll ---
class ProcessPayrollRequest(BaseModel):
    month: int = Field(..., ge=1, le=12)
    year: int = Field(..., ge=2024)
    working_days: int = Field(default=26, ge=1, le=31)


class PayslipResponse(BaseModel):
    id: uuid.UUID
    plant_id: uuid.UUID
    employee_id: uuid.UUID
    month: int
    year: int
    gross_earnings: Decimal
    overtime_earnings: Decimal
    absence_deduction: Decimal
    late_deduction: Decimal
    advance_emi_deduction: Decimal
    total_deductions: Decimal
    net_salary: Decimal
    created_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)