"""
modules/klaviyo.py — Klaviyo Email & SMS Marketing Module

Covers:
  - Account info
  - Profiles (list, get, search by email)
  - Lists (list all, get members)
  - Campaigns (list email + sms)
  - Metrics (list all 57+)
  - Events / track custom events
  - Overview (full account summary)

Requires: KLAVIYO_API_KEY env var (private API key starting with pk_)
Uses Klaviyo Python SDK v10 — responses are Pydantic model objects.
"""

import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger("gcp-bot.klaviyo")

KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")


def _client():
    if not KLAVIYO_API_KEY:
        raise RuntimeError("KLAVIYO_API_KEY is not set")
    import klaviyo_api
    return klaviyo_api.KlaviyoAPI(
        KLAVIYO_API_KEY,
        max_delay=60,
        max_retries=3,
        test_host=None,
    )


def _str(val):
    """Safely convert any value (including datetime) to string."""
    return str(val) if val is not None else None


class KlaviyoModule:

    def __init__(self):
        self._api = None

    @property
    def api(self):
        if not self._api:
            self._api = _client()
        return self._api

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        resp = self.api.Accounts.get_accounts()
        accounts = resp.data or []
        if not accounts:
            return {}
        a = accounts[0]
        ci = a.attributes.contact_information
        return {
            "id": a.id,
            "name": ci.organization_name,
            "sender_email": ci.default_sender_email,
            "sender_name": ci.default_sender_name,
            "timezone": a.attributes.timezone,
            "currency": getattr(a.attributes, "preferred_currency", None),
        }

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def list_profiles(self, page_size: int = 50) -> dict:
        resp = self.api.Profiles.get_profiles(page_size=page_size, sort="-created")
        profiles = resp.data or []
        return {
            "count": len(profiles),
            "profiles": [
                {
                    "id": p.id,
                    "email": p.attributes.email,
                    "first_name": p.attributes.first_name,
                    "last_name": p.attributes.last_name,
                    "created": _str(p.attributes.created),
                }
                for p in profiles
            ],
        }

    def get_profile(self, profile_id: str) -> dict:
        resp = self.api.Profiles.get_profile(profile_id)
        p = resp.data
        a = p.attributes
        return {
            "id": p.id,
            "email": a.email,
            "first_name": a.first_name,
            "last_name": a.last_name,
            "phone": a.phone_number,
            "location": a.location.to_dict() if a.location else None,
            "properties": a.properties,
            "created": _str(a.created),
            "updated": _str(a.updated),
        }

    def search_profile_by_email(self, email: str) -> dict:
        resp = self.api.Profiles.get_profiles(
            filter=f'equals(email,"{email}")',
            page_size=1,
        )
        profiles = resp.data or []
        if not profiles:
            return {"found": False, "email": email}
        p = profiles[0]
        a = p.attributes
        return {
            "found": True,
            "id": p.id,
            "email": a.email,
            "first_name": a.first_name,
            "last_name": a.last_name,
            "created": _str(a.created),
        }

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def list_lists(self) -> dict:
        resp = self.api.Lists.get_lists()
        lists = resp.data or []
        return {
            "count": len(lists),
            "lists": [
                {
                    "id": l.id,
                    "name": l.attributes.name,
                    "created": _str(l.attributes.created),
                    "updated": _str(l.attributes.updated),
                }
                for l in lists
            ],
        }

    def get_list_profiles(self, list_id: str, page_size: int = 50) -> dict:
        resp = self.api.Lists.get_list_profiles(list_id, page_size=page_size)
        profiles = resp.data or []
        return {
            "list_id": list_id,
            "count": len(profiles),
            "profiles": [
                {
                    "id": p.id,
                    "email": p.attributes.email,
                    "first_name": p.attributes.first_name,
                }
                for p in profiles
            ],
        }

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(self, channel: str = "email") -> dict:
        resp = self.api.Campaigns.get_campaigns(
            filter=f"equals(messages.channel,'{channel}')",
        )
        campaigns = resp.data or []
        return {
            "count": len(campaigns),
            "channel": channel,
            "campaigns": [
                {
                    "id": c.id,
                    "name": c.attributes.name,
                    "status": c.attributes.status,
                    "send_time": _str(getattr(c.attributes, "send_time", None)),
                    "scheduled_at": _str(getattr(c.attributes, "scheduled_at", None)),
                    "created_at": _str(getattr(c.attributes, "created_at", None)),
                    "updated_at": _str(getattr(c.attributes, "updated_at", None)),
                }
                for c in campaigns
            ],
        }

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def list_metrics(self) -> dict:
        resp = self.api.Metrics.get_metrics()
        metrics = resp.data or []
        return {
            "count": len(metrics),
            "metrics": [
                {
                    "id": m.id,
                    "name": m.attributes.name,
                    "integration": getattr(m.attributes, "integration", None),
                }
                for m in metrics
            ],
        }

    # ------------------------------------------------------------------
    # Events / Track
    # ------------------------------------------------------------------

    def create_event(self, event_name: str, email: str, properties: dict = None) -> dict:
        body = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {"data": {"type": "metric", "attributes": {"name": event_name}}},
                    "profile": {"data": {"type": "profile", "attributes": {"email": email}}},
                    "properties": properties or {},
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            }
        }
        self.api.Events.create_event(body=body)
        return {"status": "tracked", "event": event_name, "email": email}

    # ------------------------------------------------------------------
    # Overview
    # ------------------------------------------------------------------

    def get_overview(self) -> dict:
        try:
            account = self.get_account()
        except Exception as e:
            account = {"error": str(e)}
        try:
            lists = self.list_lists()
        except Exception as e:
            lists = {"error": str(e), "count": 0, "lists": []}
        try:
            campaigns = self.list_campaigns()
        except Exception as e:
            campaigns = {"error": str(e), "count": 0, "campaigns": []}
        try:
            metrics = self.list_metrics()
        except Exception as e:
            metrics = {"error": str(e), "count": 0}

        return {
            "account": account,
            "lists_count": lists.get("count", 0),
            "lists": lists.get("lists", []),
            "email_campaigns_count": campaigns.get("count", 0),
            "recent_campaigns": campaigns.get("campaigns", [])[:5],
            "metrics_count": metrics.get("count", 0),
        }
