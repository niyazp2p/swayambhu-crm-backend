import uuid
from typing import Annotated
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.models.procurement import Vendor, WasteGrade, GRNRecord, Batch, BatchStage
from app.schemas.procurement import (
    VendorCreate,
    VendorResponse,
    WasteGradeCreate,
    WasteGradeResponse,
    GRNCreate,
    GRNResponse,
    BatchResponse,
    BatchUpdate,
)
from app.services.procurement_service import calculate_grn_weights_and_cost

router = APIRouter()


# ----------------- VENDORS -----------------
@router.post("/vendors", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
async def create_vendor(
    vendor_in: VendorCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None, description="Plant ID override for Super Admin"),
):
    target_plant = plant_id or current_user.plant_id
    if not target_plant and current_user.role == UserRole.SUPER_ADMIN:
        target_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )

    if not target_plant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plant context required to create vendor.",
        )

    vendor = Vendor(**vendor_in.model_dump(), plant_id=target_plant)
    db.add(vendor)
    await db.commit()
    await db.refresh(vendor)
    return vendor


@router.get("/vendors", response_model=list[VendorResponse])
async def list_vendors(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = select(Vendor)
    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(Vendor.plant_id == current_user.plant_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.delete("/vendors/{vendor_id}", status_code=status.HTTP_200_OK)
async def delete_or_archive_vendor(
    vendor_id: uuid.UUID,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    vendor = await db.get(Vendor, vendor_id)
    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Vendor not found."
        )

    if current_user.role != UserRole.SUPER_ADMIN and vendor.plant_id != current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to delete vendors from other plants.",
        )

    grn_count_res = await db.execute(
        select(func.count(GRNRecord.id)).where(GRNRecord.vendor_id == vendor_id)
    )
    linked_grns = grn_count_res.scalar() or 0

    if linked_grns > 0:
        vendor.is_active = False
        await db.commit()
        return {
            "message": f"Vendor has {linked_grns} linked inward intake slips. Status changed to Inactive (Soft-Archived).",
            "action": "DEACTIVATED",
            "vendor_id": str(vendor_id),
        }

    await db.delete(vendor)
    await db.commit()
    return {
        "message": "Vendor deleted successfully from registry.",
        "action": "DELETED",
        "vendor_id": str(vendor_id),
    }


# ----------------- WASTE GRADES -----------------
@router.get("/grades", response_model=list[WasteGradeResponse])
async def list_waste_grades(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    stmt = select(WasteGrade).order_by(WasteGrade.grade_code.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/grades/{grade_id}", response_model=WasteGradeResponse)
async def get_waste_grade(
    grade_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    grade = await db.get(WasteGrade, grade_id)
    if not grade:
        raise HTTPException(status_code=404, detail="Waste grade not found.")
    return grade


@router.post("/grades", response_model=WasteGradeResponse, status_code=status.HTTP_201_CREATED)
async def create_waste_grade(
    grade_in: WasteGradeCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None, description="Plant ID override for Super Admin"),
):
    target_plant = plant_id or current_user.plant_id
    if not target_plant and current_user.role == UserRole.SUPER_ADMIN:
        target_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )

    if not target_plant:
        raise HTTPException(status_code=400, detail="Plant context required to set waste grade.")

    grade = WasteGrade(**grade_in.model_dump(), plant_id=target_plant)
    db.add(grade)
    await db.commit()
    await db.refresh(grade)
    return grade


# ----------------- GRN (INWARD INTAKE) -----------------
@router.post("/grn", response_model=GRNResponse, status_code=status.HTTP_201_CREATED)
async def create_grn_intake(
    grn_in: GRNCreate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER, UserRole.WEIGHBRIDGE_OPERATOR)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None, description="Plant ID override for Super Admin"),
):
    target_plant = plant_id or current_user.plant_id
    if not target_plant and current_user.role == UserRole.SUPER_ADMIN:
        target_plant = await db.scalar(
            select(Plant.id).where(Plant.is_active.is_(True)).limit(1)
        )

    if not target_plant:
        raise HTTPException(status_code=400, detail="Plant context required for inward intake.")

    grade_res = await db.execute(
        select(WasteGrade).where(WasteGrade.id == grn_in.waste_grade_id)
    )
    grade = grade_res.scalar_one_or_none()
    if not grade:
        raise HTTPException(status_code=404, detail="Waste grade not found.")

    try:
        calc = calculate_grn_weights_and_cost(
            gross_weight=grn_in.gross_weight,
            tare_weight=grn_in.tare_weight,
            moisture_percentage=grn_in.moisture_percentage,
            contamination_kg=grn_in.contamination_deduction_kg,
            rate_per_kg=grade.current_rate_per_kg,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    grn_num = f"GRN-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    grn = GRNRecord(
        plant_id=target_plant,
        grn_number=grn_num,
        vendor_id=grn_in.vendor_id,
        waste_grade_id=grn_in.waste_grade_id,
        vehicle_number=grn_in.vehicle_number,
        gross_weight=grn_in.gross_weight,
        tare_weight=grn_in.tare_weight,
        net_weight=calc["net_weight"],
        moisture_percentage=grn_in.moisture_percentage,
        contamination_deduction_kg=grn_in.contamination_deduction_kg,
        accepted_net_weight=calc["accepted_net_weight"],
        rate_per_kg=grade.current_rate_per_kg,
        total_payable_amount=calc["total_payable_amount"],
        is_manual_override=grn_in.is_manual_override,
        override_reason=grn_in.override_reason,
        load_photo_url=grn_in.load_photo_url,
        created_by_id=current_user.id,
    )
    db.add(grn)
    await db.flush()

    # Fixed: Populates initial_quantity_kg and is_consumed to meet schema constraints
    batch = Batch(
        plant_id=target_plant,
        batch_code=f"BATCH-RAW-{grn.grn_number}",
        grn_id=grn.id,
        stage=BatchStage.RAW,
        initial_quantity_kg=calc["accepted_net_weight"],
        current_quantity_kg=calc["accepted_net_weight"],
        is_consumed=False,
    )
    db.add(batch)

    await db.commit()
    await db.refresh(grn)
    return grn


@router.get("/grn", response_model=list[GRNResponse])
async def list_grn_records(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = 50,
    vendor_id: uuid.UUID | None = None,
):
    query = select(GRNRecord)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(GRNRecord.plant_id == current_user.plant_id)
    elif current_user.plant_id:
        query = query.where(GRNRecord.plant_id == current_user.plant_id)

    if vendor_id:
        query = query.where(GRNRecord.vendor_id == vendor_id)

    query = query.order_by(GRNRecord.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


# ----------------- INTAKE BATCHES -----------------
@router.get("/batches", response_model=list[BatchResponse])
async def list_intake_batches(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    stage: BatchStage | None = None,
    limit: int = 100,
):
    query = select(Batch)

    if current_user.role != UserRole.SUPER_ADMIN:
        query = query.where(Batch.plant_id == current_user.plant_id)
    elif current_user.plant_id:
        query = query.where(Batch.plant_id == current_user.plant_id)

    if stage:
        query = query.where(Batch.stage == stage)

    query = query.order_by(Batch.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.patch("/batches/{batch_id}/stage", response_model=BatchResponse)
async def update_batch_lifecycle(
    batch_id: uuid.UUID,
    batch_in: BatchUpdate,
    current_user: Annotated[
        User,
        Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER)),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    batch = await db.get(Batch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Batch not found."
        )

    if current_user.role != UserRole.SUPER_ADMIN and batch.plant_id != current_user.plant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Unauthorized to update batches outside assigned facility.",
        )

    if batch_in.stage is not None:
        batch.stage = batch_in.stage
    if batch_in.yard_location is not None:
        batch.yard_location = batch_in.yard_location

    await db.commit()
    await db.refresh(batch)
    return batch