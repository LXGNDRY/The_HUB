"""Small GraphQL-first Shopify client with bounded retries and typed failures."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.security import validate_shop_domain

TokenProvider = Callable[[], Awaitable[str]]


class ShopifyError(RuntimeError):
    pass


class ShopifyAuthenticationError(ShopifyError):
    pass


class ShopifyThrottledError(ShopifyError):
    pass


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.5


class ShopifyClient:
    """A tenant-bound client; callers never pass tokens to individual operations."""

    def __init__(
        self,
        shop: str,
        token_provider: TokenProvider,
        *,
        api_version: str = "2026-07",
        timeout_seconds: float = 20.0,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.shop = validate_shop_domain(shop)
        self.token_provider = token_provider
        self.endpoint = f"https://{self.shop}/admin/api/{api_version}/graphql.json"
        self.timeout = httpx.Timeout(timeout_seconds)
        self.retry_policy = retry_policy or RetryPolicy()

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.retry_policy.attempts):
            token = await self.token_provider()
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.endpoint,
                        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
                        json={"query": query, "variables": variables or {}},
                    )
                if response.status_code == 401:
                    raise ShopifyAuthenticationError("Shopify rejected the tenant access token.")
                if response.status_code == 429:
                    raise ShopifyThrottledError("Shopify throttled the operation.")
                response.raise_for_status()
                payload = response.json()
                if payload.get("errors"):
                    raise ShopifyError(f"Shopify GraphQL errors: {payload['errors']}")
                return payload.get("data", {})
            except (httpx.TransportError, ShopifyThrottledError) as exc:
                last_error = exc
                if attempt + 1 < self.retry_policy.attempts:
                    await asyncio.sleep(self.retry_policy.base_delay_seconds * (2**attempt))
        raise ShopifyError("Shopify operation exhausted its retry budget.") from last_error
