"""
Tenant management router.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant, PlanType

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    email: EmailStr
    plan: str = "core"


class TenantResponse(BaseModel):
    id: str
    name: str
    email: str
    plan: str
    shopify_store_domain: str
    billing_active: bool
    monthly_price_usd: float

    class Config:
        from_attributes = True


@router.post("/", response_model=TenantResponse)
async def create_tenant(data: TenantCreate, db: AsyncSession = Depends(get_db)):
    """Create a new tenant."""
    # Check for existing
    result = await db.execute(select(Tenant).where(Tenant.email == data.email))
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A tenant with this email already exists.")

    plan_map = {"core": PlanType.CORE, "growth": PlanType.GROWTH,
                "enterprise": PlanType.ENTERPRISE, "agency": PlanType.AGENCY}
    plan = plan_map.get(data.plan, PlanType.CORE)
    price_map = {"core": 99.0, "growth": 249.0, "enterprise": 499.0, "agency": 999.0}

    tenant = Tenant(
        name=data.name,
        email=data.email,
        plan=plan,
        monthly_price_usd=price_map.get(data.plan, 99.0),
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Get tenant details."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    return tenant


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(db: AsyncSession = Depends(get_db)):
    """List all active tenants."""
    result = await db.execute(select(Tenant).where(Tenant.is_active == True))
    return result.scalars().all()