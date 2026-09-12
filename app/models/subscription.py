"""
Subscription / billing event tracking.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class SubscriptionEvent(Base):
    """Track subscription lifecycle events (created, renewed, cancelled, failed)."""
    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # created, renewed, cancelled, past_due, payment_failed
    stripe_event_id: Mapped[str] = mapped_column(String(255), default="")
    amount_usd: Mapped[float] = mapped_column(Float, default=0.0)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AutomationJob(Base):
    """Track scheduled/running automation jobs per tenant."""
    __tablename__ = "automation_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(
        String(100), nullable=False
    )  # billing_check, gmc_sync, theme_deploy, etc.
    schedule: Mapped[str] = mapped_column(
        String(100), default="0 8 * * *"
    )  # cron expression
    last_run: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )