import io
from decimal import Decimal
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.models.hr import Employee, WageType, AttendanceRecord, AttendanceStatus, SalaryAdvance


def calculate_monthly_payroll(
    employee: Employee,
    working_days: int,
    attendance_records: list[AttendanceRecord],
    active_advance: SalaryAdvance | None,
    grace_late_count: int = 3,
) -> dict[str, Decimal]:
    """
    PRD Formula Implementation:
    - Unpaid Absence: (Base Salary / Working Days) * Unpaid Leave Days[cite: 1]
    - Late Arrival: Each late mark beyond grace_late_count incurs a half-day deduction[cite: 1]
    - Advances: Offsets monthly EMI from net pay[cite: 1]
    """
    base_rate = employee.base_rate

    # Count attendances
    unpaid_leaves = 0
    half_days = 0
    late_marks = 0
    total_ot_hours = Decimal("0.00")

    for att in attendance_records:
        if att.status in (AttendanceStatus.ABSENT, AttendanceStatus.ON_LEAVE):
            unpaid_leaves += 1
        elif att.status == AttendanceStatus.HALF_DAY:
            half_days += 1

        if att.is_late:
            late_marks += 1

        total_ot_hours += att.overtime_hours

    per_day_rate = (base_rate / Decimal(working_days)).quantize(Decimal("0.01"))

    if employee.wage_type == WageType.MONTHLY_FIXED:
        gross_earnings = base_rate
        # Absence Deduction = (Base / Working Days) * (Absences + (0.5 * HalfDays))[cite: 1]
        effective_unpaid = Decimal(unpaid_leaves) + (Decimal(half_days) * Decimal("0.5"))
        absence_deduction = (per_day_rate * effective_unpaid).quantize(Decimal("0.01"))
    else:
        # DAILY_WAGE: Earns strictly for days present[cite: 1]
        days_present = working_days - unpaid_leaves - (half_days * 0.5)
        gross_earnings = (per_day_rate * Decimal(days_present)).quantize(Decimal("0.01"))
        absence_deduction = Decimal("0.00")

    # Late marks beyond grace period deduct 0.5 day's wage per incident[cite: 1]
    excess_lates = max(0, late_marks - grace_late_count)
    late_deduction = (per_day_rate * Decimal(0.5) * Decimal(excess_lates)).quantize(Decimal("0.01"))

    # Overtime (1.5x standard hourly rate, assuming 8 hr shift)[cite: 1]
    hourly_rate = per_day_rate / Decimal("8.00")
    overtime_earnings = (total_ot_hours * hourly_rate * Decimal("1.50")).quantize(Decimal("0.01"))

    # Advance EMI[cite: 1]
    emi_deduction = Decimal("0.00")
    if active_advance and active_advance.remaining_balance > 0:
        emi_deduction = min(active_advance.monthly_emi, active_advance.remaining_balance)

    total_deductions = absence_deduction + late_deduction + emi_deduction
    net_salary = max(Decimal("0.00"), gross_earnings + overtime_earnings - total_deductions)

    return {
        "gross_earnings": gross_earnings,
        "overtime_earnings": overtime_earnings,
        "absence_deduction": absence_deduction,
        "late_deduction": late_deduction,
        "advance_emi_deduction": emi_deduction,
        "total_deductions": total_deductions,
        "net_salary": net_salary,
    }


def generate_payslip_pdf(
    employee: Employee,
    month: int,
    year: int,
    gross_earnings: Decimal,
    overtime_earnings: Decimal,
    absence_deduction: Decimal,
    late_deduction: Decimal,
    advance_emi_deduction: Decimal,
    total_deductions: Decimal,
    net_salary: Decimal,
) -> io.BytesIO:
    """Generates standard printable payslip PDF[cite: 1]."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    elements = []
    styles = getSampleStyleSheet()

    # Title
    title_style = ParagraphStyle(
        name="TitleStyle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        alignment=1,
        textColor=colors.HexColor("#1b4332"),
    )
    elements.append(Paragraph("<b>WASTE MANAGEMENT & RECYCLING ERP</b>", title_style))
    elements.append(Paragraph(f"Salary Slip - {month:02d}/{year}", styles["Normal"]))
    elements.append(Spacer(1, 15))

    # Employee Header
    emp_info = [
        [Paragraph(f"<b>Employee Name:</b> {employee.full_name}", styles["Normal"]),
         Paragraph(f"<b>Employee Code:</b> {employee.employee_code}", styles["Normal"])],
        [Paragraph(f"<b>Designation:</b> {employee.role.value}", styles["Normal"]),
         Paragraph(f"<b>Wage Model:</b> {employee.wage_type.value}", styles["Normal"])],
    ]
    emp_table = Table(emp_info, colWidths=[270, 270])
    emp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
    ]))
    elements.append(emp_table)
    elements.append(Spacer(1, 15))

    # Financial Breakdown Table
    breakdown_data = [
        ["Earnings", "Amount (INR)", "Deductions", "Amount (INR)"],
        ["Base Wages", f"{gross_earnings:.2f}", "Absence Loss", f"{absence_deduction:.2f}"],
        ["Overtime Earnings", f"{overtime_earnings:.2f}", "Late Deductions", f"{late_deduction:.2f}"],
        ["", "", "Loan/Advance EMI", f"{advance_emi_deduction:.2f}"],
        ["Total Gross", f"{(gross_earnings + overtime_earnings):.2f}", "Total Deductions", f"{total_deductions:.2f}"],
        ["", "", "NET SALARY", f"{net_salary:.2f}"],
    ]
    breakdown_table = Table(breakdown_data, colWidths=[160, 110, 160, 110])
    breakdown_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2d6a4f")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#ced4da")),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BACKGROUND', (2, -1), (-1, -1), colors.HexColor("#d8f3dc")),
        ('FONTNAME', (2, -1), (-1, -1), 'Helvetica-Bold'),
    ]))
    elements.append(breakdown_table)

    doc.build(elements)
    buffer.seek(0)
    return buffer