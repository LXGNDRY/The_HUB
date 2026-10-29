"""
Google Merchant API v1 client (replaces the Content API for Shopping, sunset 2026-08-18).

Thin REST wrapper — read helpers only. Mutating calls must go through config.safe_execute().
Auth: GCP_SA_KEY_JSON / GCP_SA_KEY (raw SA JSON), else Application Default Credentials.
"""
import json
import logging
import os

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

logger = logging.getLogger("gcp-bot.merchant_api")

BASE = "https://merchantapi.googleapis.com"
SCOPES = ["https://www.googleapis.com/auth/content"]
DEFAULT_MERCHANT_ID = "582171114"


def merchant_id() -> str:
    return os.environ.get("GMC_MERCHANT_ID") or DEFAULT_MERCHANT_ID


def _session() -> AuthorizedSession:
    raw = os.environ.get("GCP_SA_KEY_JSON") or os.environ.get("GCP_SA_KEY")
    if raw:
        creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
    else:
        creds, _ = google.auth.default(scopes=SCOPES)
    return AuthorizedSession(creds)


_SESSION = None


def get(path: str, params: dict | None = None) -> dict:
    """GET a Merchant API path (e.g. 'accounts/v1/accounts/123'). Raises RuntimeError on HTTP errors."""
    global _SESSION
    if _SESSION is None:
        _SESSION = _session()
    resp = _SESSION.get(f"{BASE}/{path}", params=params, timeout=60)
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} {path}: {resp.text[:500]}")
    return resp.json()


def list_all(path: str, key: str, page_size: int = 250, params: dict | None = None) -> list:
    """Follow nextPageToken and return every item under `key`."""
    items, token = [], None
    while True:
        q = {"pageSize": page_size, **(params or {})}
        if token:
            q["pageToken"] = token
        data = get(path, q)
        items.extend(data.get(key, []))
        token = data.get("nextPageToken")
        if not token:
            return items


def account(mid: str | None = None) -> dict:
    return get(f"accounts/v1/accounts/{mid or merchant_id()}")


def account_issues(mid: str | None = None) -> list:
    return list_all(f"accounts/v1/accounts/{mid or merchant_id()}/issues", "accountIssues")


def shipping_settings(mid: str | None = None) -> dict:
    return get(f"accounts/v1/accounts/{mid or merchant_id()}/shippingSettings")


def products(mid: str | None = None) -> list:
    """All products incl. productStatus (approval + item-level issues)."""
    return list_all(f"products/v1/accounts/{mid or merchant_id()}/products", "products")


def data_sources(mid: str | None = None) -> list:
    return list_all(f"datasources/v1/accounts/{mid or merchant_id()}/dataSources", "dataSources")


def account_services(mid: str | None = None) -> list:
    """Linked services (e.g. Google Ads links)."""
    return list_all(f"accounts/v1/accounts/{mid or merchant_id()}/services", "accountServices")


def flat_rate(service_rate_group: dict) -> str | None:
    """Return a GMC rate group's flat price as a decimal string, 'NO_SHIPPING', or None if not flat."""
    single = service_rate_group.get("singleValue", {})
    if single.get("noShipping"):
        return "NO_SHIPPING"
    micros = single.get("flatRate", {}).get("amountMicros")
    return None if micros is None else f"{int(micros) / 1_000_000:.2f}"
