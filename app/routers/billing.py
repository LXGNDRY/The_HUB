"""
Billing router — Stripe subscription management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.tenant import Tenant, PlanType

router = APIRouter()


class ChangePlan(BaseModel):
    plan: str


PRICE_MAP = {
    "core": {"price": 99.0, "stripe_price_id": None},  # Set via env
    "growth": {"price": 249.0, "stripe_price_id": None},
    "enterprise": {"price": 499.0, "stripe_price_id": None},
    "agency": {"price": 999.0, "stripe_price_id": None},
}


@router.post("/create-checkout/{tenant_id}")
async def create_checkout_session(tenant_id: str, plan: str = "core"):
    """Create a Stripe Checkout session for a tenant."""
    from app.services.stripe_service import create_checkout_session
    session = await create_checkout_session(tenant_id, plan)
    return {"checkout_url": session.url}


@router.post("/webhook")
async def stripe_webhook(payload: dict):
    """Handle incoming Stripe webhook events."""
    from app.services.stripe_service import handle_webhook
    result = await handle_webhook(payload)
    return {"received": True, "result": result}


@router.get("/plan/{tenant_id}")
async def get_plan(tenant_id: str, db: AsyncSession = Depends(get_db)):
    """Get current subscription plan."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Tenant not found.")
    return {
        "plan": tenant.plan.value if hasattr(tenant.plan, 'value') else tenant.plan,
        "active": tenant.billing_active,
        "price_usd": tenant.monthly_price_usd,
    }