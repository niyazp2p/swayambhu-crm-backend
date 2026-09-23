from fastapi import APIRouter
from app.api.v1.endpoints import auth, procurement, hr, operations, analytics, sales, inventory, financials,users

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users & RBAC"])
api_router.include_router(procurement.router, prefix="/procurement", tags=["Procurement & Inventory"])
api_router.include_router(hr.router, prefix="/hr", tags=["HR & Payroll"])
api_router.include_router(operations.router, prefix="/operations", tags=["Operations & DPR"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics & Yield Intelligence"])
api_router.include_router(sales.router, prefix="/sales", tags=["Sales & Outward Dispatch"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["Finished Goods Inventory"])
api_router.include_router(financials.router, prefix="/financials", tags=["Plant Financials & P&L"])