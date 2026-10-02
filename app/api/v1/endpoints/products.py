import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.product import (
    MaterialCategory,
    MaterialSubCategory,
    Product,
    ProductMaterialComposition,
    WeightUnit,
)
from app.models.user import User
from app.schemas.product import (
    MaterialCategoryCreate,
    MaterialCategoryResponse,
    MaterialSubCategoryCreate,
    MaterialSubCategoryResponse,
    ProductCreate,
    ProductMaterialResponse,
    ProductResponse,
    ProductUpdate,
    QuantityUpdate,
)
from app.services.product_document_service import ProductDocumentService

router = APIRouter()


# ===========================================================================
# 1. STATIC MASTER ROUTES (Declared first to avoid /{product_id} collision)
# ===========================================================================

@router.get("/categories", response_model=list[MaterialCategoryResponse])
async def list_material_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Retrieve all parent material categories."""
    stmt = select(MaterialCategory).order_by(MaterialCategory.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/categories", response_model=MaterialCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_material_category(
    cat_in: MaterialCategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Register a new parent material scrap category."""
    existing = await db.scalar(
        select(MaterialCategory).where(MaterialCategory.name.ilike(cat_in.name.strip()))
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category '{cat_in.name}' already exists.",
        )

    category = MaterialCategory(
        name=cat_in.name.strip(),
        description=cat_in.description.strip() if cat_in.description else None,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


@router.get("/sub-categories", response_model=list[MaterialSubCategoryResponse])
async def list_material_sub_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    category_id: uuid.UUID | None = Query(None, description="Optional category filter"),
):
    """Retrieve all material subcategories (Polyal, HM, Tube, etc.)."""
    stmt = select(MaterialSubCategory)
    if category_id:
        stmt = stmt.where(MaterialSubCategory.category_id == category_id)
    stmt = stmt.order_by(MaterialSubCategory.name.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/sub-categories", response_model=MaterialSubCategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_material_sub_category(
    sub_in: MaterialSubCategoryCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Register a new material subcategory classification."""
    category = await db.get(MaterialCategory, sub_in.category_id)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parent material category not found.",
        )

    existing = await db.scalar(
        select(MaterialSubCategory).where(MaterialSubCategory.code == sub_in.code.strip().upper())
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Subcategory code '{sub_in.code}' already exists.",
        )

    sub = MaterialSubCategory(
        category_id=sub_in.category_id,
        name=sub_in.name.strip(),
        code=sub_in.code.strip().upper(),
        description=sub_in.description.strip() if sub_in.description else None,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


# ===========================================================================
# 2. ROOT COLLECTION ROUTES
# ===========================================================================

@router.get("", response_model=list[ProductResponse])
async def list_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """List all circular upcycled products with eager-loaded material compositions."""
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .order_by(Product.created_at.desc())
    )
    res = await db.execute(stmt)
    products = res.scalars().all()

    # Normalize response to match ProductMaterialResponse shape
    response_list = []
    for prod in products:
        mats = [
            ProductMaterialResponse(
                id=m.id,
                sub_category_id=m.sub_category_id,
                sub_category_name=m.sub_category.name if m.sub_category else "Unknown",
                sub_category_code=m.sub_category.code if m.sub_category else "N/A",
                weight=m.weight,
                unit=m.unit,
                percentage_share=m.percentage_share,
            )
            for m in prod.materials_used
        ]
        response_list.append(
            ProductResponse(
                id=prod.id,
                sku=prod.sku,
                name=prod.name,
                description=prod.description,
                dimensions=prod.dimensions,
                total_quantity=prod.total_quantity,
                unit_measure=prod.unit_measure,
                total_weight_kg=prod.total_weight_kg,
                is_active=prod.is_active,
                materials_used=mats,
                created_at=prod.created_at,
                updated_at=prod.updated_at,
            )
        )
    return response_list


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    prod_in: ProductCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Create a new product with itemized material breakdown and auto-calculated mass balance."""
    # Check for SKU collision
    existing = await db.scalar(
        select(Product).where(Product.sku == prod_in.sku.strip().upper())
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product SKU '{prod_in.sku}' already exists.",
        )

    # Compute aggregate unit weight in KG
    total_weight = Decimal("0.000")
    for mat in prod_in.materials:
        w_kg = mat.weight if mat.unit == WeightUnit.KG else (mat.weight / Decimal("1000.00"))
        total_weight += w_kg

    product = Product(
        sku=prod_in.sku.strip().upper(),
        name=prod_in.name.strip(),
        description=prod_in.description.strip() if prod_in.description else None,
        dimensions=prod_in.dimensions.strip() if prod_in.dimensions else None,
        total_quantity=prod_in.total_quantity,
        unit_measure=prod_in.unit_measure,
        total_weight_kg=total_weight,
    )
    db.add(product)
    await db.flush()

    # Link material compositions & calculate percentage shares
    for mat in prod_in.materials:
        w_kg = mat.weight if mat.unit == WeightUnit.KG else (mat.weight / Decimal("1000.00"))
        share = (
            ((w_kg / total_weight) * Decimal("100.00")).quantize(Decimal("0.01"))
            if total_weight > 0
            else Decimal("0.00")
        )

        comp = ProductMaterialComposition(
            product_id=product.id,
            sub_category_id=mat.sub_category_id,
            weight=mat.weight,
            unit=mat.unit,
            percentage_share=share,
        )
        db.add(comp)

    await db.commit()

    # Reload product with joined relationships
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .where(Product.id == product.id)
    )
    res = await db.execute(stmt)
    prod = res.scalar_one()

    mats = [
        ProductMaterialResponse(
            id=m.id,
            sub_category_id=m.sub_category_id,
            sub_category_name=m.sub_category.name if m.sub_category else "Unknown",
            sub_category_code=m.sub_category.code if m.sub_category else "N/A",
            weight=m.weight,
            unit=m.unit,
            percentage_share=m.percentage_share,
        )
        for m in prod.materials_used
    ]

    return ProductResponse(
        id=prod.id,
        sku=prod.sku,
        name=prod.name,
        description=prod.description,
        dimensions=prod.dimensions,
        total_quantity=prod.total_quantity,
        unit_measure=prod.unit_measure,
        total_weight_kg=prod.total_weight_kg,
        is_active=prod.is_active,
        materials_used=mats,
        created_at=prod.created_at,
        updated_at=prod.updated_at,
    )


# ===========================================================================
# 3. DYNAMIC UUID ENDPOINTS (Must stay below literal path endpoints)
# ===========================================================================

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get single product details with complete material formulation."""
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .where(Product.id == product_id)
    )
    res = await db.execute(stmt)
    prod = res.scalar_one_or_none()
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    mats = [
        ProductMaterialResponse(
            id=m.id,
            sub_category_id=m.sub_category_id,
            sub_category_name=m.sub_category.name if m.sub_category else "Unknown",
            sub_category_code=m.sub_category.code if m.sub_category else "N/A",
            weight=m.weight,
            unit=m.unit,
            percentage_share=m.percentage_share,
        )
        for m in prod.materials_used
    ]

    return ProductResponse(
        id=prod.id,
        sku=prod.sku,
        name=prod.name,
        description=prod.description,
        dimensions=prod.dimensions,
        total_quantity=prod.total_quantity,
        unit_measure=prod.unit_measure,
        total_weight_kg=prod.total_weight_kg,
        is_active=prod.is_active,
        materials_used=mats,
        created_at=prod.created_at,
        updated_at=prod.updated_at,
    )


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    prod_in: ProductUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Update core attributes of a product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    for field, val in prod_in.model_dump(exclude_unset=True).items():
        setattr(product, field, val)

    await db.commit()

    # Re-fetch eager
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
        )
        .where(Product.id == product_id)
    )
    res = await db.execute(stmt)
    prod = res.scalar_one()

    mats = [
        ProductMaterialResponse(
            id=m.id,
            sub_category_id=m.sub_category_id,
            sub_category_name=m.sub_category.name if m.sub_category else "Unknown",
            sub_category_code=m.sub_category.code if m.sub_category else "N/A",
            weight=m.weight,
            unit=m.unit,
            percentage_share=m.percentage_share,
        )
        for m in prod.materials_used
    ]

    return ProductResponse(
        id=prod.id,
        sku=prod.sku,
        name=prod.name,
        description=prod.description,
        dimensions=prod.dimensions,
        total_quantity=prod.total_quantity,
        unit_measure=prod.unit_measure,
        total_weight_kg=prod.total_weight_kg,
        is_active=prod.is_active,
        materials_used=mats,
        created_at=prod.created_at,
        updated_at=prod.updated_at,
    )


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Remove product and cascade linked composition rows."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    await db.delete(product)
    await db.commit()


@router.get("/{product_id}/materials", response_model=list[ProductMaterialResponse])
@router.get("/{product_id}/materials/weights", response_model=list[ProductMaterialResponse])
async def get_product_materials(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Retrieve material formulation and weight breakdown for a product."""
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


@router.get("/{product_id}/pdf")
async def generate_product_pdf(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Stream generated ReportLab Product Specification PDF."""
    stmt = (
        select(Product)
        .options(
            selectinload(Product.materials_used)
            .joinedload(ProductMaterialComposition.sub_category)
            .joinedload(MaterialSubCategory.category)
        )
        .where(Product.id == product_id)
    )
    res = await db.execute(stmt)
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")

    pdf_buffer = ProductDocumentService.generate_product_spec_pdf(product)
    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=SpecSheet_{product.sku}.pdf"},
    )


@router.get("/{product_id}/quantity")
async def get_product_quantity(
    product_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Get active stock quantity for a product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return {
        "id": product.id,
        "sku": product.sku,
        "total_quantity": product.total_quantity,
        "unit_measure": product.unit_measure,
    }


@router.put("/{product_id}/quantity")
async def update_product_quantity(
    product_id: uuid.UUID,
    qty_in: QuantityUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Adjust active inventory count for a product."""
    product = await db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found.")
    product.total_quantity = qty_in.total_quantity
    await db.commit()
    return {"message": "Quantity updated successfully", "total_quantity": product.total_quantity}