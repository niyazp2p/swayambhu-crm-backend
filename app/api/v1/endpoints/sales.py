import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.models.procurement import WasteGrade
from app.models.inventory import FinishedGoodsInventory
from app.models.sales import Buyer, DispatchOrder, DispatchStatus, PaymentStatus
from app.schemas.sales import (
    BuyerCreate,
    BuyerUpdate,
    BuyerResponse,
    DispatchOrderCreate,
    DispatchOrderResponse,
    PaymentUpdate,
)
from app.services.document_service import DocumentService

router = APIRouter()


async def _resolve_plant_context(
    current_user: User, plant_id: uuid.UUID | None, db: AsyncSession
) -> uuid.UUID:
    """Safely retrieves target plant context or defaults to the first active plant for Super Admins."""
    if current_user.role == UserRole.SUPER_ADMIN:
        if plant_id:
            return plant_id
        active_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )
        if not active_plant:
            active_plant = await db.scalar(select(Plant.id).limit(1))
        if not active_plant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active plant found in database.",
            )
        return active_plant

    if not current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is not bound to an operational facility.",
        )
    return current_user.plant_id


# ---------------------------------------------------------------------------
# Buyer Management
# ---------------------------------------------------------------------------

@router.post("/buyers", response_model=BuyerResponse, status_code=status.HTTP_201_CREATED)
async def create_buyer(
    buyer_in: BuyerCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER, UserRole.SALES_LOGISTICS)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    buyer = Buyer(**buyer_in.model_dump())
    db.add(buyer)
    await db.commit()
    await db.refresh(buyer)
    return buyer


@router.get("/buyers", response_model=list[BuyerResponse])
async def list_buyers(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    search: str | None = None,
    is_active: bool = True,
):
    stmt = select(Buyer).where(Buyer.is_active == is_active)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where((Buyer.name.ilike(pattern)) | (Buyer.contact_phone.ilike(pattern)))
    stmt = stmt.order_by(Buyer.name.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/buyers/{buyer_id}", response_model=BuyerResponse)
async def get_buyer(
    buyer_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    buyer = await db.get(Buyer, buyer_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found.")
    return buyer


@router.patch("/buyers/{buyer_id}", response_model=BuyerResponse)
async def update_buyer(
    buyer_id: uuid.UUID,
    buyer_in: BuyerUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    buyer = await db.get(Buyer, buyer_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer not found.")

    for field, value in buyer_in.model_dump(exclude_unset=True).items():
        setattr(buyer, field, value)

    await db.commit()
    await db.refresh(buyer)
    return buyer


# ---------------------------------------------------------------------------
# Outward Dispatch & Gate Pass
# ---------------------------------------------------------------------------

@router.post("/dispatch", response_model=DispatchOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_dispatch_order(
    dispatch_in: DispatchOrderCreate,
    current_user: Annotated[
        User,
        Depends(
            require_roles(
                UserRole.SUPER_ADMIN,
                UserRole.PLANT_MANAGER,
                UserRole.WEIGHBRIDGE_OPERATOR,
                UserRole.SALES_LOGISTICS,
            )
        ),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(
        None, description="Target plant UUID (Super Admin cross-facility assignment)"
    ),
):
    # 1. Safely resolve Plant Context with automatic fallback for Super Admin
    target_plant_id = await _resolve_plant_context(current_user, plant_id, db)

    # 2. Weighbridge Invariance
    if dispatch_in.gross_weight_kg <= dispatch_in.tare_weight_kg:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gross weight must exceed tare weight.",
        )

    # 3. Verify Foreign Entities
    buyer = await db.get(Buyer, dispatch_in.buyer_id)
    if not buyer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Buyer entity not found.")

    grade = await db.get(WasteGrade, dispatch_in.waste_grade_id)
    if not grade:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Waste grade classification not found.")

    net_weight = dispatch_in.gross_weight_kg - dispatch_in.tare_weight_kg

    # 4. Inventory Validation & Row Lock (of=FinishedGoodsInventory prevents outer join errors)
    inv_stmt = (
        select(FinishedGoodsInventory)
        .where(
            FinishedGoodsInventory.plant_id == target_plant_id,
            FinishedGoodsInventory.waste_grade_id == dispatch_in.waste_grade_id,
        )
        .with_for_update(of=FinishedGoodsInventory)
    )
    inv_res = await db.execute(inv_stmt)
    stock_record = inv_res.scalar_one_or_none()

    if not stock_record or stock_record.current_stock_kg < net_weight:
        available_kg = stock_record.current_stock_kg if stock_record else Decimal("0.00")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Insufficient finished inventory for grade '{grade.grade_code}'. "
                f"Requested: {net_weight} kg, Available: {available_kg} kg."
            ),
        )

    # 5. Deduct Finished Stock Ledger
    stock_record.current_stock_kg -= net_weight
    if dispatch_in.bales_count > 0:
        stock_record.bales_in_stock = max(0, stock_record.bales_in_stock - dispatch_in.bales_count)

    # 6. Commercial & GST Tax Formulation
    taxable_val = (net_weight * dispatch_in.rate_per_kg).quantize(Decimal("0.01"))
    gst_factor = (dispatch_in.gst_rate_percent / Decimal("100.00")).quantize(Decimal("0.0001"))

    if dispatch_in.is_interstate:
        cgst_rate = sgst_rate = Decimal("0.00")
        cgst_amt = sgst_amt = Decimal("0.00")
        igst_rate = dispatch_in.gst_rate_percent
        igst_amt = (taxable_val * gst_factor).quantize(Decimal("0.01"))
    else:
        cgst_rate = (dispatch_in.gst_rate_percent / Decimal("2.0")).quantize(Decimal("0.01"))
        sgst_rate = cgst_rate
        igst_rate = Decimal("0.00")
        cgst_amt = (taxable_val * (cgst_rate / Decimal("100.00"))).quantize(Decimal("0.01"))
        sgst_amt = (taxable_val * (sgst_rate / Decimal("100.00"))).quantize(Decimal("0.01"))
        igst_amt = Decimal("0.00")

    total_amount = (taxable_val + cgst_amt + sgst_amt + igst_amt).quantize(Decimal("0.01"))
    dispatch_number = f"DSP-{uuid.uuid4().hex[:8].upper()}"

    # 7. Persist Dispatch Record
    dispatch = DispatchOrder(
        dispatch_number=dispatch_number,
        plant_id=target_plant_id,
        buyer_id=dispatch_in.buyer_id,
        waste_grade_id=dispatch_in.waste_grade_id,
        operator_id=current_user.id,
        vehicle_number=dispatch_in.vehicle_number.strip().upper(),
        driver_name=dispatch_in.driver_name,
        driver_phone=dispatch_in.driver_phone,
        transporter_name=dispatch_in.transporter_name,
        eway_bill_number=dispatch_in.eway_bill_number,
        tare_weight_kg=dispatch_in.tare_weight_kg,
        gross_weight_kg=dispatch_in.gross_weight_kg,
        net_weight_kg=net_weight,
        bales_count=dispatch_in.bales_count,
        rate_per_kg=dispatch_in.rate_per_kg,
        taxable_amount=taxable_val,
        cgst_rate=cgst_rate,
        cgst_amount=cgst_amt,
        sgst_rate=sgst_rate,
        sgst_amount=sgst_amt,
        igst_rate=igst_rate,
        igst_amount=igst_amt,
        total_amount=total_amount,
        amount_paid=Decimal("0.00"),
        status=DispatchStatus.DISPATCHED,
        payment_status=PaymentStatus.UNPAID,
        dispatch_date=dispatch_in.dispatch_date or date.today(),
        remarks=dispatch_in.remarks,
    )
    db.add(dispatch)
    await db.commit()

    # Eager reload for serializable response
    final_query = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
        .where(DispatchOrder.id == dispatch.id)
    )
    result = await db.execute(final_query)
    return result.scalar_one()


@router.get("/dispatch", response_model=list[DispatchOrderResponse])
async def list_dispatch_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = None,
    buyer_id: uuid.UUID | None = None,
    payment_status: PaymentStatus | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
    )

    if current_user.role == UserRole.SUPER_ADMIN:
        if plant_id:
            query = query.where(DispatchOrder.plant_id == plant_id)
    else:
        query = query.where(DispatchOrder.plant_id == current_user.plant_id)

    if buyer_id:
        query = query.where(DispatchOrder.buyer_id == buyer_id)
    if payment_status:
        query = query.where(DispatchOrder.payment_status == payment_status)
    if from_date:
        query = query.where(DispatchOrder.dispatch_date >= from_date)
    if to_date:
        query = query.where(DispatchOrder.dispatch_date <= to_date)

    query = (
        query.order_by(DispatchOrder.dispatch_date.desc(), DispatchOrder.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/dispatch/{dispatch_id}", response_model=DispatchOrderResponse)
async def get_dispatch_order(
    dispatch_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
        .where(DispatchOrder.id == dispatch_id)
    )
    result = await db.execute(stmt)
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch order not found.")

    if current_user.role != UserRole.SUPER_ADMIN and dispatch.plant_id != current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to dispatch records within assigned facility.",
        )

    return dispatch


# ---------------------------------------------------------------------------
# Settlements & Financial Receipts
# ---------------------------------------------------------------------------

@router.post("/dispatch/{dispatch_id}/payment", response_model=DispatchOrderResponse)
async def record_buyer_payment(
    dispatch_id: uuid.UUID,
    payment_in: PaymentUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER, UserRole.SALES_LOGISTICS)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
        .where(DispatchOrder.id == dispatch_id)
        .with_for_update(of=DispatchOrder)
    )
    result = await db.execute(stmt)
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch order not found.")

    if current_user.role != UserRole.SUPER_ADMIN and dispatch.plant_id != current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to dispatch records within assigned facility.",
        )

    new_total_paid = (dispatch.amount_paid + payment_in.payment_amount).quantize(Decimal("0.01"))
    if new_total_paid > dispatch.total_amount:
        remaining = dispatch.total_amount - dispatch.amount_paid
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment exceeds remaining balance. Max payable amount: ₹{remaining}",
        )

    dispatch.amount_paid = new_total_paid
    if dispatch.amount_paid >= dispatch.total_amount:
        dispatch.payment_status = PaymentStatus.PAID
    else:
        dispatch.payment_status = PaymentStatus.PARTIAL

    if payment_in.payment_reference:
        ref_note = f" [Ref: {payment_in.payment_reference}]"
        dispatch.remarks = f"{dispatch.remarks or ''}{ref_note}".strip()

    await db.commit()
    await db.refresh(dispatch)
    return dispatch


# ---------------------------------------------------------------------------
# PDF Document Gate Pass & Tax Invoice Streams
# ---------------------------------------------------------------------------

@router.get("/dispatch/{dispatch_id}/gate-pass")
async def download_gate_pass_pdf(
    dispatch_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
        .where(DispatchOrder.id == dispatch_id)
    )
    result = await db.execute(stmt)
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch order not found.")

    pdf_stream = DocumentService.generate_gate_pass_pdf(
        dispatch=dispatch,
        plant=dispatch.plant,
        grade=dispatch.waste_grade,
    )

    return StreamingResponse(
        pdf_stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=GatePass_{dispatch.dispatch_number}.pdf"},
    )


@router.get("/dispatch/{dispatch_id}/invoice")
async def download_tax_invoice_pdf(
    dispatch_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = (
        select(DispatchOrder)
        .options(
            selectinload(DispatchOrder.buyer),
            selectinload(DispatchOrder.plant),
            selectinload(DispatchOrder.waste_grade),
        )
        .where(DispatchOrder.id == dispatch_id)
    )
    result = await db.execute(stmt)
    dispatch = result.scalar_one_or_none()

    if not dispatch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch order not found.")

    pdf_stream = DocumentService.generate_invoice_pdf(
        dispatch=dispatch,
        plant=dispatch.plant,
        grade=dispatch.waste_grade,
    )

    return StreamingResponse(
        pdf_stream,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=TaxInvoice_{dispatch.dispatch_number}.pdf"},
    )