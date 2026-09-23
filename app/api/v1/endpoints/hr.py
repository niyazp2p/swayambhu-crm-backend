import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.models.hr import (
    Employee,
    EmployeeRole,
    WageType,
    AttendanceRecord,
    AttendanceStatus,
    SalaryAdvance,
    AdvanceStatus,
    Payslip,
)
from app.schemas.hr import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    AttendanceCreate,
    AttendanceBulkCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AdvanceCreate,
    AdvanceResponse,
    AdvanceSettlement,
    ProcessPayrollRequest,
    PayslipResponse,
)
from app.services.payroll_service import calculate_monthly_payroll, generate_payslip_pdf

router = APIRouter()


async def _resolve_plant_id(
    db: AsyncSession, current_user: User, explicit_plant_id: uuid.UUID | None = None
) -> uuid.UUID:
    """
    Resolves the facility context. If operating as Super Admin and no plant_id
    is explicitly supplied, automatically falls back to the first active plant.
    """
    target_plant = explicit_plant_id or current_user.plant_id

    if not target_plant and current_user.role == UserRole.SUPER_ADMIN:
        default_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active == True).limit(1)
        )
        target_plant = default_plant

    if not target_plant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plant context required. No active facility found in system.",
        )
    return target_plant


# =====================================================================
# 1. EMPLOYEES DIRECTORY
# =====================================================================

@router.post("/employees", response_model=EmployeeResponse, status_code=status.HTTP_201_CREATED)
async def create_employee(
    emp_in: EmployeeCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
):
    target_plant = await _resolve_plant_id(db, current_user, plant_id)

    existing = await db.scalar(select(Employee).where(Employee.employee_code == emp_in.employee_code))
    if existing:
        raise HTTPException(status_code=400, detail="Employee code already registered.")

    employee = Employee(**emp_in.model_dump(), plant_id=target_plant)
    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return employee


@router.get("/employees", response_model=list[EmployeeResponse])
async def list_employees(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    role: EmployeeRole | None = None,
    wage_type: WageType | None = None,
    is_active: bool | None = None,
    plant_id: uuid.UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(Employee)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(Employee.plant_id == current_user.plant_id)
    elif plant_id:
        query = query.where(Employee.plant_id == plant_id)

    if role is not None:
        query = query.where(Employee.role == role)
    if wage_type is not None:
        query = query.where(Employee.wage_type == wage_type)
    if is_active is not None:
        query = query.where(Employee.is_active == is_active)

    query = query.order_by(Employee.employee_code.asc()).limit(limit).offset(offset)
    res = await db.execute(query)
    return res.scalars().all()


@router.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    employee = await db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if current_user.role != UserRole.SUPER_ADMIN and employee.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized plant access.")

    return employee


@router.patch("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: uuid.UUID,
    emp_update: EmployeeUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    employee = await db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if current_user.role != UserRole.SUPER_ADMIN and employee.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized across plants.")

    for field, val in emp_update.model_dump(exclude_unset=True).items():
        setattr(employee, field, val)

    await db.commit()
    await db.refresh(employee)
    return employee


@router.delete("/employees/{employee_id}", response_model=EmployeeResponse)
async def deactivate_employee(
    employee_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    employee = await db.get(Employee, employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    if current_user.role != UserRole.SUPER_ADMIN and employee.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized across plants.")

    employee.is_active = False
    await db.commit()
    await db.refresh(employee)
    return employee


# =====================================================================
# 2. DAILY ATTENDANCE TRACKER
# =====================================================================

@router.get("/attendance", response_model=list[AttendanceResponse])
async def list_attendance(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    attendance_date: date | None = None,
    employee_id: uuid.UUID | None = None,
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2024),
    plant_id: uuid.UUID | None = Query(None),
):
    query = select(AttendanceRecord)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(AttendanceRecord.plant_id == current_user.plant_id)
    elif plant_id:
        query = query.where(AttendanceRecord.plant_id == plant_id)

    if attendance_date:
        query = query.where(AttendanceRecord.attendance_date == attendance_date)
    if employee_id:
        query = query.where(AttendanceRecord.employee_id == employee_id)
    if month:
        query = query.where(extract("month", AttendanceRecord.attendance_date) == month)
    if year:
        query = query.where(extract("year", AttendanceRecord.attendance_date) == year)

    res = await db.execute(query.order_by(AttendanceRecord.attendance_date.desc()))
    return res.scalars().all()


@router.post("/attendance", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
async def log_single_attendance(
    att_in: AttendanceCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    employee = await db.get(Employee, att_in.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    target_plant = current_user.plant_id or employee.plant_id

    existing = await db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == att_in.employee_id,
            AttendanceRecord.attendance_date == att_in.attendance_date,
        )
    )
    if existing:
        raise HTTPException(status_code=400, detail="Attendance already recorded for this date.")

    record = AttendanceRecord(**att_in.model_dump(), plant_id=target_plant)
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


@router.post("/attendance/bulk", response_model=list[AttendanceResponse], status_code=status.HTTP_201_CREATED)
async def log_bulk_attendance(
    bulk_in: AttendanceBulkCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    committed_records = []
    for att in bulk_in.records:
        employee = await db.get(Employee, att.employee_id)
        if not employee:
            continue

        target_plant = current_user.plant_id or employee.plant_id

        existing = await db.scalar(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == att.employee_id,
                AttendanceRecord.attendance_date == att.attendance_date,
            )
        )
        if existing:
            existing.status = att.status
            existing.check_in = att.check_in
            existing.check_out = att.check_out
            existing.is_late = att.is_late
            existing.overtime_hours = att.overtime_hours
            committed_records.append(existing)
        else:
            rec = AttendanceRecord(**att.model_dump(), plant_id=target_plant)
            db.add(rec)
            committed_records.append(rec)

    await db.commit()
    for r in committed_records:
        await db.refresh(r)
    return committed_records


@router.patch("/attendance/{attendance_id}", response_model=AttendanceResponse)
async def update_attendance_record(
    attendance_id: uuid.UUID,
    att_up: AttendanceUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    record = await db.get(AttendanceRecord, attendance_id)
    if not record:
        raise HTTPException(status_code=404, detail="Attendance record not found.")

    if current_user.role != UserRole.SUPER_ADMIN and record.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized plant access.")

    for field, val in att_up.model_dump(exclude_unset=True).items():
        setattr(record, field, val)

    await db.commit()
    await db.refresh(record)
    return record


# =====================================================================
# 3. SALARY ADVANCES & LOANS
# =====================================================================

@router.get("/advances", response_model=list[AdvanceResponse])
async def list_advances(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    status: AdvanceStatus | None = None,
    employee_id: uuid.UUID | None = None,
    plant_id: uuid.UUID | None = Query(None),
):
    query = select(SalaryAdvance)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(SalaryAdvance.plant_id == current_user.plant_id)
    elif plant_id:
        query = query.where(SalaryAdvance.plant_id == plant_id)

    if status:
        query = query.where(SalaryAdvance.status == status)
    if employee_id:
        query = query.where(SalaryAdvance.employee_id == employee_id)

    res = await db.execute(query.order_by(SalaryAdvance.created_at.desc()))
    return res.scalars().all()


@router.post("/advances", response_model=AdvanceResponse, status_code=status.HTTP_201_CREATED)
async def issue_advance(
    adv_in: AdvanceCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    employee = await db.get(Employee, adv_in.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    target_plant = current_user.plant_id or employee.plant_id

    active_loan = await db.scalar(
        select(SalaryAdvance).where(
            SalaryAdvance.employee_id == adv_in.employee_id,
            SalaryAdvance.status == AdvanceStatus.ACTIVE,
        )
    )
    if active_loan:
        raise HTTPException(
            status_code=400,
            detail=f"Employee already has an active advance with balance ₹{active_loan.remaining_balance:.2f}",
        )

    monthly_emi = (adv_in.principal_amount / Decimal(adv_in.tenure_months)).quantize(Decimal("0.01"))
    advance = SalaryAdvance(
        plant_id=target_plant,
        employee_id=adv_in.employee_id,
        principal_amount=adv_in.principal_amount,
        tenure_months=adv_in.tenure_months,
        monthly_emi=monthly_emi,
        remaining_balance=adv_in.principal_amount,
    )
    db.add(advance)
    await db.commit()
    await db.refresh(advance)
    return advance


@router.patch("/advances/{advance_id}/settle", response_model=AdvanceResponse)
async def settle_advance_manually(
    advance_id: uuid.UUID,
    settlement: AdvanceSettlement,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    advance = await db.get(SalaryAdvance, advance_id)
    if not advance:
        raise HTTPException(status_code=404, detail="Advance record not found.")

    if current_user.role != UserRole.SUPER_ADMIN and advance.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized plant access.")

    advance.remaining_balance = max(Decimal("0.00"), advance.remaining_balance - settlement.settlement_amount)
    if advance.remaining_balance <= Decimal("0.00"):
        advance.status = AdvanceStatus.REPAID

    await db.commit()
    await db.refresh(advance)
    return advance


# =====================================================================
# 4. PAYROLL & PAYSLIPS
# =====================================================================

@router.get("/payslips", response_model=list[PayslipResponse])
async def list_payslips(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2024),
    employee_id: uuid.UUID | None = None,
    plant_id: uuid.UUID | None = Query(None),
):
    query = select(Payslip).where(Payslip.month == month, Payslip.year == year)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(Payslip.plant_id == current_user.plant_id)
    elif plant_id:
        query = query.where(Payslip.plant_id == plant_id)

    if employee_id:
        query = query.where(Payslip.employee_id == employee_id)

    res = await db.execute(query.order_by(Payslip.created_at.desc()))
    return res.scalars().all()


@router.post("/payroll/process", response_model=list[PayslipResponse])
async def process_monthly_payroll(
    payroll_req: ProcessPayrollRequest,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.HR_OFFICER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
):
    target_plant = await _resolve_plant_id(db, current_user, plant_id)

    emp_res = await db.execute(
        select(Employee).where(Employee.plant_id == target_plant, Employee.is_active == True)
    )
    employees = emp_res.scalars().all()

    created_payslips = []

    for emp in employees:
        att_res = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.employee_id == emp.id,
                extract("month", AttendanceRecord.attendance_date) == payroll_req.month,
                extract("year", AttendanceRecord.attendance_date) == payroll_req.year,
            )
        )
        attendance = att_res.scalars().all()

        adv_res = await db.execute(
            select(SalaryAdvance).where(
                SalaryAdvance.employee_id == emp.id,
                SalaryAdvance.status == AdvanceStatus.ACTIVE,
            )
        )
        active_advance = adv_res.scalar_one_or_none()

        payroll = calculate_monthly_payroll(
            employee=emp,
            working_days=payroll_req.working_days,
            attendance_records=attendance,
            active_advance=active_advance,
        )

        # Clear existing payslip for same month/year if re-running
        existing_slip = await db.scalar(
            select(Payslip).where(
                Payslip.employee_id == emp.id,
                Payslip.month == payroll_req.month,
                Payslip.year == payroll_req.year,
            )
        )
        if existing_slip:
            await db.delete(existing_slip)
            await db.flush()

        payslip = Payslip(
            plant_id=target_plant,
            employee_id=emp.id,
            month=payroll_req.month,
            year=payroll_req.year,
            **payroll,
        )
        db.add(payslip)

        if active_advance and payroll["advance_emi_deduction"] > 0:
            active_advance.remaining_balance -= payroll["advance_emi_deduction"]
            if active_advance.remaining_balance <= Decimal("0.00"):
                active_advance.status = AdvanceStatus.REPAID

        created_payslips.append(payslip)

    await db.commit()
    for p in created_payslips:
        await db.refresh(p)
    return created_payslips


@router.get("/payslip/{payslip_id}", response_model=PayslipResponse)
async def get_payslip_detail(
    payslip_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payslip = await db.get(Payslip, payslip_id)
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found.")

    if current_user.role != UserRole.SUPER_ADMIN and payslip.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized plant access.")

    return payslip


@router.get("/payslip/{payslip_id}/pdf")
async def download_payslip_pdf(
    payslip_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    payslip = await db.get(Payslip, payslip_id)
    if not payslip:
        raise HTTPException(status_code=404, detail="Payslip not found.")

    if current_user.role != UserRole.SUPER_ADMIN and payslip.plant_id != current_user.plant_id:
        raise HTTPException(status_code=403, detail="Unauthorized plant access.")

    employee = await db.get(Employee, payslip.employee_id)
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found.")

    pdf_buffer = generate_payslip_pdf(
        employee=employee,
        month=payslip.month,
        year=payslip.year,
        gross_earnings=payslip.gross_earnings,
        overtime_earnings=payslip.overtime_earnings,
        absence_deduction=payslip.absence_deduction,
        late_deduction=payslip.late_deduction,
        advance_emi_deduction=payslip.advance_emi_deduction,
        total_deductions=payslip.total_deductions,
        net_salary=payslip.net_salary,
    )

    filename = f"payslip_{employee.employee_code}_{payslip.month:02d}_{payslip.year}.pdf"
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )