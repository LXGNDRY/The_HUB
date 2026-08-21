import base64
import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app.core.security import (
    create_oauth_state,
    parse_oauth_state,
    validate_shop_domain,
    verify_shopify_oauth_query,
    verify_shopify_webhook,
)


def test_shop_domain_is_normalized():
    assert validate_shop_domain("My-Store.myshopify.com") == "my-store.myshopify.com"


@pytest.mark.parametrize("shop", ["example.com", "https://x.myshopify.com", "x.myshopify.com.evil.test", ""])
def test_invalid_shop_domains_are_rejected(shop):
    with pytest.raises(HTTPException):
        validate_shop_domain(shop)


def test_shopify_webhook_hmac():
    body = b'{"id": 1}'
    secret = "secret"
    signature = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    assert verify_shopify_webhook(body, signature, secret)
    assert not verify_shopify_webhook(body + b"x", signature, secret)


def test_oauth_query_hmac():
    query = {"code": "abc", "shop": "demo.myshopify.com", "state": "nonce"}
    message = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    query["hmac"] = hmac.new(b"secret", message.encode(), hashlib.sha256).hexdigest()
    assert verify_shopify_oauth_query(query, "secret")


def test_signed_oauth_state_round_trip():
    state = create_oauth_state("tenant-1", "demo.myshopify.com", "signing-secret")
    parsed = parse_oauth_state(state, "signing-secret")
    assert parsed.tenant_id == "tenant-1"
    assert parsed.shop == "demo.myshopify.com"


def test_tampered_oauth_state_is_rejected():
    state = create_oauth_state("tenant-1", "demo.myshopify.com", "signing-secret")
    with pytest.raises(HTTPException):
        parse_oauth_state(state[:-2] + "xx", "signing-secret")
