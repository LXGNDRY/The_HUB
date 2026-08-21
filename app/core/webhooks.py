"""Webhook verification and replay-protection contracts."""

from __future__ import annotations

import hashlib
import hmac
from typing import Protocol


class EventStore(Protocol):
    async def claim(self, provider: str, event_id: str) -> bool:
        """Atomically claim an event. Return False when already processed."""


class InMemoryEventStore:
    """Development-only implementation; production must use a durable database."""

    def __init__(self) -> None:
        self._events: set[tuple[str, str]] = set()

    async def claim(self, provider: str, event_id: str) -> bool:
        key = (provider, event_id)
        if key in self._events:
            return False
        self._events.add(key)
        return True


def verify_hex_signature(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return bool(signature and secret) and hmac.compare_digest(expected, signature)
