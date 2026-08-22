"""Stripe checkout and verified subscription lifecycle handling."""

import uuid

import stripe
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.subscription import SubscriptionEvent
from app.models.tenant import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_checkout_session(tenant_id: str, plan: str) -> object:
    price_map = {
        "core": settings.STRIPE_PRICE_CORE,
        "growth": settings.STRIPE_PRICE_GROWTH,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
        "agency": settings.STRIPE_PRICE_AGENCY,
    }
    price_id = price_map.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")
    return stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"tenant_id": tenant_id, "plan": plan},
        success_url=f"{settings.DASHBOARD_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.DASHBOARD_URL}/pricing",
    )


async def handle_verified_webhook(event: dict, db: AsyncSession) -> dict:
    event_type = str(event.get("type", "unknown"))
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {}) or {}
    tenant_raw = metadata.get("tenant_id")
    tenant = None
    tenant_id = None
    if tenant_raw:
        try:
            tenant_id = uuid.UUID(str(tenant_raw))
        except ValueError:
            return {"event": event_type, "handled": False, "reason": "invalid_tenant"}
        tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        customer_id = str(data.get("customer", ""))
        subscription_id = str(data.get("subscription", "") or data.get("id", ""))
        predicates = []
        if customer_id:
            predicates.append(Tenant.stripe_customer_id == customer_id)
        if subscription_id:
            predicates.append(Tenant.stripe_subscription_id == subscription_id)
        if predicates:
            tenant = (
                await db.execute(select(Tenant).where(or_(*predicates)))
            ).scalar_one_or_none()
        tenant_id = tenant.id if tenant else None
    if tenant is None:
        return {"event": event_type, "handled": False, "reason": "unknown_tenant"}

    if event_type == "checkout.session.completed":
        tenant.stripe_customer_id = str(data.get("customer", ""))
        tenant.stripe_subscription_id = str(data.get("subscription", ""))
        tenant.billing_active = True
    elif event_type == "customer.subscription.updated":
        tenant.billing_active = str(data.get("status", "")) in {"active", "trialing"}
    elif event_type == "customer.subscription.deleted":
        tenant.billing_active = False
    elif event_type == "invoice.payment_failed":
        tenant.billing_active = False
    else:
        return {"event": event_type, "handled": False}

    db.add(
        SubscriptionEvent(
            tenant_id=tenant_id,
            event_type=event_type,
            stripe_event_id=str(event.get("id", "")),
            amount_usd=float(data.get("amount_paid", 0) or 0) / 100,
            success=event_type != "invoice.payment_failed",
        )
    )
    await db.commit()
    return {"event": event_type, "handled": True, "tenant_id": str(tenant_id)}
