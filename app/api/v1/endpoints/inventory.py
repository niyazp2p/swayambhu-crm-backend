import uuid
from decimal import Decimal
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_roles
from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.plant import Plant
from app.models.procurement import WasteGrade
from app.models.inventory import FinishedGoodsInventory, StockLedger, StockMovementType
from app.schemas.inventory import (
    InventoryStockResponse,
    PaginatedStockResponse,
    StockAdjustmentCreate,
    StockLedgerResponse,
)

router = APIRouter()


async def _resolve_plant_context(current_user: User, plant_id: uuid.UUID | None, db: AsyncSession) -> uuid.UUID:
    """Safely retrieves target plant context or defaults to the first active plant for Super Admins."""
    if current_user.role == UserRole.SUPER_ADMIN:
        if plant_id:
            return plant_id
        active_plant_query = await db.execute(select(Plant.id).where(Plant.is_active.is_(True)).limit(1))
        first_plant = active_plant_query.scalar_one_or_none()
        if not first_plant:
            raise HTTPException(status_code=400, detail="No active plant found for cross-plant reporting.")
        return first_plant
    if not current_user.plant_id:
        raise HTTPException(status_code=403, detail="User account is not bound to an operational facility.")
    return current_user.plant_id


@router.get("/stock", response_model=PaginatedStockResponse)
async def get_current_stock(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None, description="Plant ID (Super Admin override)"),
    search: str | None = Query(None, description="Search by grade code or category"),
    category: str | None = Query(None, description="Filter by category (e.g., Plastic, Metal)"),
):
    target_plant = await _resolve_plant_context(current_user, plant_id, db)

    # Fetch inventory rows joined with waste grades
    stmt = (
        select(
            FinishedGoodsInventory.id,
            FinishedGoodsInventory.plant_id,
            FinishedGoodsInventory.waste_grade_id,
            WasteGrade.grade_code,
            WasteGrade.category_name,
            FinishedGoodsInventory.current_stock_kg,
            FinishedGoodsInventory.bales_in_stock,
            WasteGrade.current_rate_per_kg,
            FinishedGoodsInventory.updated_at,
        )
        .join(WasteGrade, FinishedGoodsInventory.waste_grade_id == WasteGrade.id)
        .where(FinishedGoodsInventory.plant_id == target_plant)
    )

    if category:
        stmt = stmt.where(WasteGrade.category_name.ilike(f"%{category}%"))
    if search:
        stmt = stmt.where(
            (WasteGrade.grade_code.ilike(f"%{search}%")) | (WasteGrade.category_name.ilike(f"%{search}%"))
        )

    stmt = stmt.order_by(WasteGrade.category_name.asc(), WasteGrade.grade_code.asc())
    result = await db.execute(stmt)
    rows = result.all()

    items = []
    total_kg = Decimal("0.00")
    total_bales = 0
    total_valuation = Decimal("0.00")

    for row in rows:
        stock_kg = row[5]
        bales = row[6]
        rate_per_kg = row[7]
        valuation = (stock_kg * rate_per_kg).quantize(Decimal("0.01"))

        total_kg += stock_kg
        total_bales += bales
        total_valuation += valuation

        items.append(
            InventoryStockResponse(
                id=row[0],
                plant_id=row[1],
                waste_grade_id=row[2],
                waste_grade_code=row[3],
                category_name=row[4],
                current_stock_kg=stock_kg,
                bales_in_stock=bales,
                current_valuation_inr=valuation,
                updated_at=row[8],
            )
        )

    return PaginatedStockResponse(
        total_grades=len(items),
        total_stock_kg=total_kg.quantize(Decimal("0.01")),
        total_bales=total_bales,
        total_valuation_inr=total_valuation.quantize(Decimal("0.01")),
        items=items,
    )


@router.post("/adjustments", response_model=InventoryStockResponse)
async def adjust_stock_balance(
    payload: StockAdjustmentCreate,
    current_user: Annotated[User, Depends(require_roles(UserRole.SUPER_ADMIN, UserRole.PLANT_MANAGER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
):
    """Audited physical re-count and stock write-off adjustment with row locking."""
    target_plant = await _resolve_plant_context(current_user, plant_id, db)

    # Lock row to prevent concurrent race conditions
    stmt = (
        select(FinishedGoodsInventory)
        .where(
            FinishedGoodsInventory.plant_id == target_plant,
            FinishedGoodsInventory.waste_grade_id == payload.waste_grade_id,
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    inventory = result.scalar_one_or_none()

    if not inventory:
        inventory = FinishedGoodsInventory(
            plant_id=target_plant,
            waste_grade_id=payload.waste_grade_id,
            current_stock_kg=Decimal("0.00"),
            bales_in_stock=0,
        )
        db.add(inventory)
        await db.flush()

    delta_weight = payload.adjusted_weight_kg - inventory.current_stock_kg
    delta_bales = payload.adjusted_bales - inventory.bales_in_stock

    # Apply adjustments
    inventory.current_stock_kg = payload.adjusted_weight_kg
    inventory.bales_in_stock = payload.adjusted_bales

    # Write immutable ledger record
    ledger_entry = StockLedger(
        inventory_id=inventory.id,
        movement_type=StockMovementType.STOCK_ADJUSTMENT,
        delta_weight_kg=delta_weight,
        delta_bales=delta_bales,
        balance_weight_kg=inventory.current_stock_kg,
        balance_bales=inventory.bales_in_stock,
        reference_id=None,
        remarks=payload.remarks,
        actor_id=current_user.id,
    )
    db.add(ledger_entry)

    await db.commit()
    await db.refresh(inventory)

    # Fetch Grade Details for serialization
    grade_stmt = select(WasteGrade).where(WasteGrade.id == payload.waste_grade_id)
    grade = (await db.execute(grade_stmt)).scalar_one()

    return InventoryStockResponse(
        id=inventory.id,
        plant_id=inventory.plant_id,
        waste_grade_id=inventory.waste_grade_id,
        waste_grade_code=grade.grade_code,
        category_name=grade.category_name,
        current_stock_kg=inventory.current_stock_kg,
        bales_in_stock=inventory.bales_in_stock,
        current_valuation_inr=(inventory.current_stock_kg * grade.current_rate_per_kg).quantize(Decimal("0.01")),
        updated_at=inventory.updated_at,
    )


@router.get("/ledger/{grade_id}", response_model=list[StockLedgerResponse])
async def get_grade_stock_ledger(
    grade_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    plant_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Retrieves the full audit movement history for a waste grade."""
    target_plant = await _resolve_plant_context(current_user, plant_id, db)

    stmt = (
        select(StockLedger)
        .join(FinishedGoodsInventory, StockLedger.inventory_id == FinishedGoodsInventory.id)
        .where(
            FinishedGoodsInventory.plant_id == target_plant,
            FinishedGoodsInventory.waste_grade_id == grade_id,
        )
        .order_by(StockLedger.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()