"""Validated runtime configuration for the multi-tenant hub-backend."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_origins(value: object) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return list(value or [])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=True)

    APP_NAME: str = "The HUB — Shopify Operations Platform"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    SAAS_ENABLED: bool = False
    HUB_ADMIN_API_KEY: str = ""
    OAUTH_STATE_SIGNING_KEY: str = ""
    SESSION_SIGNING_KEY: str = ""
    SESSION_ISSUER: str = "the-hub"
    SESSION_AUDIENCE: str = "hub-backend"
    ALLOWED_ORIGINS: Annotated[list[str], BeforeValidator(_split_origins)] = Field(default_factory=list)

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/the_hub"

    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_CORE: str = ""
    STRIPE_PRICE_GROWTH: str = ""
    STRIPE_PRICE_ENTERPRISE: str = ""
    STRIPE_PRICE_AGENCY: str = ""

    SHOPIFY_CLIENT_ID: str = ""
    SHOPIFY_CLIENT_SECRET: str = ""
    SHOPIFY_REDIRECT_URI: str = ""

    GCP_PROJECT_ID: str = ""
    KLAVIYO_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    DOMAIN: str = "legendary-branding.com"
    DASHBOARD_URL: str = "https://legendary-branding.com"

    @property
    def production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @model_validator(mode="after")
    def validate_security_posture(self) -> "Settings":
        if self.production:
            if self.DEBUG:
                raise ValueError("DEBUG must be false in production")
            if "*" in self.ALLOWED_ORIGINS:
                raise ValueError("Wildcard CORS is forbidden in production")
            if self.SAAS_ENABLED and len(self.HUB_ADMIN_API_KEY) < 32:
                raise ValueError("HUB_ADMIN_API_KEY must contain at least 32 characters")
            if self.SAAS_ENABLED and len(self.OAUTH_STATE_SIGNING_KEY) < 32:
                raise ValueError("OAUTH_STATE_SIGNING_KEY must contain at least 32 characters")
            if self.SAAS_ENABLED and len(self.SESSION_SIGNING_KEY) < 32:
                raise ValueError("SESSION_SIGNING_KEY must contain at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
