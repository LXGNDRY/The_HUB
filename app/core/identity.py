"""Signed session authentication and tenant authorization dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database import get_db


def _decode_segment(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class Principal:
    subject: str
    email: str
    roles: frozenset[str]

    @property
    def system_admin(self) -> bool:
        return "system_admin" in self.roles


def decode_session_token(token: str) -> Principal:
    """Validate a minimal HS256 JWT issued by the configured identity boundary."""
    try:
        header_raw, payload_raw, signature_raw = token.split(".")
        header = json.loads(_decode_segment(header_raw))
        payload = json.loads(_decode_segment(payload_raw))
        signature = _decode_segment(signature_raw)
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.")
    if header.get("alg") != "HS256" or not settings.SESSION_SIGNING_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.")
    signed = f"{header_raw}.{payload_raw}".encode()
    expected = hmac.new(settings.SESSION_SIGNING_KEY.encode(), signed, hashlib.sha256).digest()
    now = int(time.time())
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token.")
    if payload.get("iss") != settings.SESSION_ISSUER or payload.get("aud") != settings.SESSION_AUDIENCE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session claims.")
    if int(payload.get("exp", 0)) <= now or int(payload.get("nbf", 0)) > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired session token.")
    subject = str(payload.get("sub", ""))
    if not subject:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing session subject.")
    return Principal(
        subject=subject,
        email=str(payload.get("email", "")),
        roles=frozenset(str(role) for role in payload.get("roles", [])),
    )


def get_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required.")
    return principal


PrincipalDependency = Annotated[Principal, Depends(get_principal)]
DatabaseDependency = Annotated[AsyncSession, Depends(get_db)]


async def require_tenant_access(
    tenant_id: uuid.UUID,
    principal: PrincipalDependency,
    db: DatabaseDependency,
) -> Principal:
    if principal.system_admin:
        return principal
    from app.models.identity import Membership, User

    query = (
        select(Membership.id)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
            User.external_subject == principal.subject,
            User.is_active.is_(True),
        )
    )
    if (await db.execute(query)).scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied.")
    return principal
