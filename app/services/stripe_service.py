"""
Stripe service — checkout, subscriptions, webhooks.
"""

import stripe
from app.core.config import settings

stripe.api_key = settings.STRIPE_SECRET_KEY


async def create_checkout_session(tenant_id: str, plan: str) -> object:
    """Create a Stripe Checkout session for a new subscription."""
    price_map = {
        "core": settings.STRIPE_PRICE_CORE,
        "growth": settings.STRIPE_PRICE_GROWTH,
        "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
        "agency": settings.STRIPE_PRICE_AGENCY,
    }
    price_id = price_map.get(plan)
    if not price_id:
        raise ValueError(f"Unknown plan: {plan}")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"tenant_id": tenant_id, "plan": plan},
        success_url=f"{settings.DASHBOARD_URL}/dashboard?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.DASHBOARD_URL}/pricing",
    )
    return session


async def handle_webhook(payload: dict) -> dict:
    """Process Stripe webhook events."""
    event_type = payload.get("type", "unknown")
    data = payload.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        tenant_id = data.get("metadata", {}).get("tenant_id")
        customer_id = data.get("customer")
        subscription_id = data.get("subscription")
        # TODO: Update tenant in DB with stripe_customer_id and stripe_subscription_id
        return {"event": "checkout.completed", "tenant_id": tenant_id}

    elif event_type == "customer.subscription.updated":
        return {"event": "subscription.updated"}

    elif event_type == "customer.subscription.deleted":
        return {"event": "subscription.deleted"}

    elif event_type == "invoice.payment_failed":
        return {"event": "payment.failed"}

    return {"event": event_type, "handled": False}