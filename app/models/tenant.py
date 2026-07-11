"""
Tenant model — multi-tenant store configuration.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Float, Text, DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base
import enum


class PlanType(str, enum.Enum):
    CORE = "core"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"
    AGENCY = "agency"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # ── Shopify ──
    shopify_store_domain: Mapped[str] = mapped_column(String(255), default="")
    shopify_access_token: Mapped[str] = mapped_column(String(512), default="")
    shopify_shop_name: Mapped[str] = mapped_column(String(255), default="")

    # ── GCP ──
    gcp_project_id: Mapped[str] = mapped_column(String(255), default="")
    gcp_service_account_json: Mapped[str] = mapped_column(Text, default="")

    # ── Klaviyo ──
    klaviyo_api_key: Mapped[str] = mapped_column(String(512), default="")

    # ── Billing ──
    plan: Mapped[PlanType] = mapped_column(
        SAEnum(PlanType), default=PlanType.CORE
    )
    stripe_customer_id: Mapped[str] = mapped_column(String(255), default="")
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), default="")
    billing_active: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_price_usd: Mapped[float] = mapped_column(Float, default=99.0)

    # ── Settings ──
    budget_threshold: Mapped[float] = mapped_column(Float, default=100.0)
    idle_cpu_threshold: Mapped[float] = mapped_column(Float, default=2.0)
    snapshot_max_age_days: Mapped[int] = mapped_column(Float, default=30)

    # ── Timestamps ──
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)