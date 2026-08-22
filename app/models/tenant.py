"""Tenant configuration; provider secret material is stored outside the database."""

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, Float, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanType(str, enum.Enum):
    CORE = "core"
    GROWTH = "growth"
    ENTERPRISE = "enterprise"
    AGENCY = "agency"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    shopify_store_domain: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    shopify_shop_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    gcp_project_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    plan: Mapped[PlanType] = mapped_column(SAEnum(PlanType), default=PlanType.CORE, nullable=False)
    stripe_customer_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    stripe_subscription_id: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    billing_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    monthly_price_usd: Mapped[float] = mapped_column(Float, default=99.0, nullable=False)
    budget_threshold: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    idle_cpu_threshold: Mapped[float] = mapped_column(Float, default=2.0, nullable=False)
    snapshot_max_age_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
