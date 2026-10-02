import uuid
from typing import Annotated
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.models.product import (
    Product,
    ProductMaterialComposition,
    MaterialSubCategory,
    WeightUnit,
)
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    QuantityUpdate,
    ProductMaterialResponse,
    MaterialSubCategoryCreate,
    MaterialSubCategoryResponse,
)
from app.services.product_document_service import ProductDocumentService
from app.models.product import MaterialCategory
router = APIRouter()


# ---------------------------------------------------------------------------
# Master: Material Subcategories (Polyal, HM, Tube, etc.)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# List all Products
# ---------------------------------------------------------------------------
@router.get("", response_model=list[ProductResponse])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .order_by(Product.created_at.desc())
    )
    res = await db.execute(stmt)
    return res.scalars().all()


# ---------------------------------------------------------------------------
# Get Single Product by ID
# ---------------------------------------------------------------------------
@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .where(Product.id == product_id)
    )
    res = await db.execute(stmt)
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product

@router.get("/categories")
async def list_material_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = select(MaterialCategory).order_by(MaterialCategory.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()

@router.post("/sub-categories", response_model=MaterialSubCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_material_sub_category(
    sub_in: MaterialSubCategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    sub = MaterialSubCategory(**sub_in.model_dump())
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


@router.get("/sub-categories", response_model=list[MaterialSubCategoryResponse])
async def list_material_sub_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = select(MaterialSubCategory).order_by(MaterialSubCategory.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


# ---------------------------------------------------------------------------
# 1. Create Product (with Material & Weights)
# ---------------------------------------------------------------------------
@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    prod_in: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    # Compute total weight in KG
    total_weight = Decimal("0.000")
    for mat in prod_in.materials:
        w_kg = mat.weight if mat.unit == WeightUnit.KG else (mat.weight / Decimal("1000.00"))
        total_weight += w_kg

    product = Product(
        sku=prod_in.sku.strip().upper(),
        name=prod_in.name,
        description=prod_in.description,
        dimensions=prod_in.dimensions,
        total_quantity=prod_in.total_quantity,
        unit_measure=prod_in.unit_measure,
        total_weight_kg=total_weight,
    )
    db.add(product)
    await db.flush()

    # Add materials used
    for mat in prod_in.materials:
        w_kg = mat.weight if mat.unit == WeightUnit.KG else (mat.weight / Decimal("1000.00"))
        share = ((w_kg / total_weight) * Decimal("100.00")).quantize(Decimal("0.01")) if total_weight > 0 else Decimal("0.00")
        
        comp = ProductMaterialComposition(
            product_id=product.id,
            sub_category_id=mat.sub_category_id,
            weight=mat.weight,
            unit=mat.unit,
            percentage_share=share,
        )
        db.add(comp)

    await db.commit()

    # Re-fetch eager
    stmt = select(Product).options(selectinload(Product.materials_used).joinedload(ProductMaterialComposition.sub_category)).where(Product.id == product.id)
    res = await db.execute(stmt)
    return res.scalar_one()


# ---------------------------------------------------------------------------
# 2. Update Product Details
# ---------------------------------------------------------------------------
@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    prod_in: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    for field, val in prod_in.model_dump(exclude_unset=True).items():
        setattr(product, field, val)

    await db.commit()
    await db.refresh(product)
    return product


# ---------------------------------------------------------------------------
# 3. Delete Product
# ---------------------------------------------------------------------------
@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    await db.delete(product)
    await db.commit()


# ---------------------------------------------------------------------------
# 4 & 5. Get Materials Used & Weights
# ---------------------------------------------------------------------------
@router.get("/{product_id}/materials", response_model=list[ProductMaterialResponse])
@router.get("/{product_id}/materials/weights", response_model=list[ProductMaterialResponse])
async def get_product_materials(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(ProductMaterialComposition)
        .options(selectinload(ProductMaterialComposition.sub_category))
        .where(ProductMaterialComposition.product_id == product_id)
    )
    res = await db.execute(stmt)
    records = res.scalars().all()

    return [
        ProductMaterialResponse(
            id=item.id,
            sub_category_id=item.sub_category_id,
            sub_category_name=item.sub_category.name if item.sub_category else "Unknown",
            sub_category_code=item.sub_category.code if item.sub_category else "N/A",
            weight=item.weight,
            unit=item.unit,
            percentage_share=item.percentage_share,
        )
        for item in records
    ]


# ---------------------------------------------------------------------------
# 6. PDF Generation
# ---------------------------------------------------------------------------
@router.get("/{product_id}/pdf")
async def generate_product_pdf(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used).joinedload(ProductMaterialComposition.sub_category).joinedload(MaterialSubCategory.category)
        )
        .where(Product.id == product_id)
    )
    res = await db.execute(stmt)
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")

    pdf_buffer = ProductDocumentService.generate_product_spec_pdf(product)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=SpecSheet_{product.sku}.pdf"},
    )


# ---------------------------------------------------------------------------
# 7. Get / Update Quantity
# ---------------------------------------------------------------------------
@router.get("/{product_id}/quantity")
async def get_product_quantity(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return {"id": product.id, "sku": product.sku, "total_quantity": product.total_quantity, "unit_measure": product.unit_measure}


@router.put("/{product_id}/quantity")
async def update_product_quantity(
    product_id: uuid.UUID,
    qty_in: QuantityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    product.total_quantity = qty_in.total_quantity
    await db.commit()
    return {"message": "Quantity updated successfully", "total_quantity": product.total_quantity}