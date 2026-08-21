"""Tenant management with principal and membership enforcement."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.identity import Principal, get_principal, require_tenant_access
from app.database import get_db
from app.models.identity import Membership, User
from app.models.tenant import PlanType, Tenant

router = APIRouter()


class TenantCreate(BaseModel):
    name: str
    email: EmailStr
    plan: PlanType = PlanType.CORE


class TenantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    email: str
    plan: PlanType
    shopify_store_domain: str
    billing_active: bool
    monthly_price_usd: float


@router.post("/", response_model=TenantResponse)
async def create_tenant(
    data: TenantCreate,
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    if not principal.system_admin:
        raise HTTPException(status_code=403, detail="System administrator access required.")
    if (await db.execute(select(Tenant.id).where(Tenant.email == data.email))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A tenant with this email already exists.")
    prices = {
        PlanType.CORE: 99.0,
        PlanType.GROWTH: 249.0,
        PlanType.ENTERPRISE: 499.0,
        PlanType.AGENCY: 999.0,
    }
    tenant = Tenant(
        name=data.name,
        email=data.email,
        plan=data.plan,
        monthly_price_usd=prices[data.plan],
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    principal: Principal = Depends(require_tenant_access),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return tenant


@router.get("/", response_model=list[TenantResponse])
async def list_tenants(
    principal: Principal = Depends(get_principal),
    db: AsyncSession = Depends(get_db),
):
    if principal.system_admin:
        query = select(Tenant).where(Tenant.is_active.is_(True))
    else:
        query = (
            select(Tenant)
            .join(Membership, Membership.tenant_id == Tenant.id)
            .join(User, User.id == Membership.user_id)
            .where(
                User.external_subject == principal.subject,
                User.is_active.is_(True),
                Membership.is_active.is_(True),
                Tenant.is_active.is_(True),
            )
        )
    return (await db.execute(query)).scalars().all()
