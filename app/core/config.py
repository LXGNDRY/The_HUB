"""
The HUB — Central configuration.
Reads from environment variables with sensible defaults.
"""

import os
from typing import Optional


class Settings:
    # ── App ──
    APP_NAME: str = "The HUB — Shopify Operations Platform"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("DASHBOARD_API_KEY", "change-me-in-production")
    ALLOWED_ORIGINS: list = os.getenv("ALLOWED_ORIGINS", "*").split(",")

    # ── Database (Cloud SQL PostgreSQL) ──
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://user:pass@localhost:5432/the_hub",
    )

    # ── Stripe ──
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    STRIPE_PRICE_CORE: str = os.getenv("STRIPE_PRICE_CORE", "")       # $99/mo
    STRIPE_PRICE_GROWTH: str = os.getenv("STRIPE_PRICE_GROWTH", "")   # $249/mo
    STRIPE_PRICE_ENTERPRISE: str = os.getenv("STRIPE_PRICE_ENTERPRISE", "")  # $499/mo
    STRIPE_PRICE_AGENCY: str = os.getenv("STRIPE_PRICE_AGENCY", "")   # $999/mo

    # ── Shopify OAuth ──
    SHOPIFY_CLIENT_ID: str = os.getenv("SHOPIFY_CLIENT_ID", "")
    SHOPIFY_CLIENT_SECRET: str = os.getenv("SHOPIFY_CLIENT_SECRET", "")
    SHOPIFY_REDIRECT_URI: str = os.getenv(
        "SHOPIFY_REDIRECT_URI",
        "https://legendary-branding.com/api/auth/shopify/callback",
    )

    # ── GCP ──
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv(
        "GOOGLE_APPLICATION_CREDENTIALS", ""
    )

    # ── Klaviyo ──
    KLAVIYO_API_KEY: str = os.getenv("KLAVIYO_API_KEY", "")

    # ── Gemini AI ──
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    # ── Scheduler ──
    BUDGET_THRESHOLD: float = float(os.getenv("BUDGET_THRESHOLD", "100.0"))
    IDLE_CPU_THRESHOLD: float = float(os.getenv("IDLE_CPU_THRESHOLD", "2.0"))
    SNAPSHOT_MAX_AGE_DAYS: int = int(os.getenv("SNAPSHOT_MAX_AGE_DAYS", "30"))

    # ── Domain ──
    DOMAIN: str = os.getenv("DOMAIN", "legendary-branding.com")
    DASHBOARD_URL: str = os.getenv(
        "DASHBOARD_URL", "https://legendary-branding.com"
    )


settings = Settings()