"""Subscription API. Provider events are accepted only by the verified webhook router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tenant import Tenant

router = APIRouter()


@router.post("/create-checkout/{tenant_id}")
async def create_checkout_session(tenant_id: str, plan: str = "core"):
    from app.services.stripe_service import create_checkout_session

    session = await create_checkout_session(tenant_id, plan)
    return {"checkout_url": session.url}


@router.get("/plan/{tenant_id}")
async def get_plan(tenant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    return {
        "plan": tenant.plan.value if hasattr(tenant.plan, "value") else tenant.plan,
        "active": tenant.billing_active,
        "price_usd": tenant.monthly_price_usd,
    }
