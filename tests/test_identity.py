import base64
import hashlib
import hmac
import json
import time

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.identity import decode_session_token


def _segment(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")


def _token(secret: str, **overrides) -> str:
    now = int(time.time())
    payload = {
        "sub": "user-123",
        "email": "owner@example.com",
        "roles": ["operator"],
        "iss": "test-issuer",
        "aud": "test-audience",
        "nbf": now - 1,
        "exp": now + 300,
        **overrides,
    }
    unsigned = f'{_segment({"alg": "HS256", "typ": "JWT"})}.{_segment(payload)}'
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode(), unsigned.encode(), hashlib.sha256).digest()
    ).decode().rstrip("=")
    return f"{unsigned}.{signature}"


def test_valid_session_token(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "s" * 40)
    monkeypatch.setattr(settings, "SESSION_ISSUER", "test-issuer")
    monkeypatch.setattr(settings, "SESSION_AUDIENCE", "test-audience")
    principal = decode_session_token(_token("s" * 40))
    assert principal.subject == "user-123"
    assert "operator" in principal.roles


def test_tampered_session_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "s" * 40)
    monkeypatch.setattr(settings, "SESSION_ISSUER", "test-issuer")
    monkeypatch.setattr(settings, "SESSION_AUDIENCE", "test-audience")
    token = _token("s" * 40)
    with pytest.raises(HTTPException):
        decode_session_token(token[:-2] + "xx")


def test_expired_session_token_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_SIGNING_KEY", "s" * 40)
    monkeypatch.setattr(settings, "SESSION_ISSUER", "test-issuer")
    monkeypatch.setattr(settings, "SESSION_AUDIENCE", "test-audience")
    with pytest.raises(HTTPException):
        decode_session_token(_token("s" * 40, exp=int(time.time()) - 1))
