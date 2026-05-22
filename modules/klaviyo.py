"""
modules/klaviyo.py — Klaviyo Email & SMS Marketing Module

Covers:
  - Profiles (list, get, create, update)
  - Lists (list all, get members, add/remove profiles)
  - Campaigns (list, get metrics)
  - Events / track (order placed, product viewed, etc.)
  - Metrics (list, get aggregate stats)
  - Flow summary
  - Account overview

Requires: KLAVIYO_API_KEY env var (private API key starting with pk_)
"""

import os
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("gcp-bot.klaviyo")

KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")

# Klaviyo API revision — pin to stable release
API_REVISION = "2024-10-15"


def _client():
    """Return a configured Klaviyo API client wrapper."""
    if not KLAVIYO_API_KEY:
        raise RuntimeError("KLAVIYO_API_KEY is not set")
    import klaviyo_api
    return klaviyo_api.KlaviyoAPI(
        KLAVIYO_API_KEY,
        max_delay=60,
        max_retries=3,
        test_host=None,
    )


class KlaviyoModule:
    """
    High-level Klaviyo operations for the GCP Bot.
    """

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
        """Return basic account info."""
        resp = self.api.Accounts.get_accounts()
        accounts = resp.get("data", [])
        if not accounts:
            return {}
        a = accounts[0]
        attrs = a.get("attributes", {})
        return {
            "id": a.get("id"),
            "name": attrs.get("contact_information", {}).get("organization_name", ""),
            "email": attrs.get("contact_information", {}).get("email", ""),
            "timezone": attrs.get("timezone", ""),
            "currency": attrs.get("preferred_currency", ""),
        }

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    def list_profiles(self, page_size: int = 50) -> dict:
        """Return a page of profiles."""
        resp = self.api.Profiles.get_profiles(
            page_size=page_size,
            sort="-created",
        )
        profiles = resp.get("data", [])
        return {
            "count": len(profiles),
            "profiles": [
                {
                    "id": p.get("id"),
                    "email": p.get("attributes", {}).get("email", ""),
                    "first_name": p.get("attributes", {}).get("first_name", ""),
                    "last_name": p.get("attributes", {}).get("last_name", ""),
                    "created": p.get("attributes", {}).get("created", ""),
                    "subscriptions": p.get("attributes", {}).get("subscriptions", {}),
                }
                for p in profiles
            ],
        }

    def get_profile(self, profile_id: str) -> dict:
        """Get a single profile by ID."""
        resp = self.api.Profiles.get_profile(profile_id)
        p = resp.get("data", {})
        attrs = p.get("attributes", {})
        return {
            "id": p.get("id"),
            "email": attrs.get("email", ""),
            "first_name": attrs.get("first_name", ""),
            "last_name": attrs.get("last_name", ""),
            "phone": attrs.get("phone_number", ""),
            "location": attrs.get("location", {}),
            "properties": attrs.get("properties", {}),
            "created": attrs.get("created", ""),
            "updated": attrs.get("updated", ""),
            "subscriptions": attrs.get("subscriptions", {}),
        }

    def search_profile_by_email(self, email: str) -> dict:
        """Find a profile by email address."""
        resp = self.api.Profiles.get_profiles(
            filter=f'equals(email,"{email}")',
            page_size=1,
        )
        profiles = resp.get("data", [])
        if not profiles:
            return {"found": False, "email": email}
        p = profiles[0]
        attrs = p.get("attributes", {})
        return {
            "found": True,
            "id": p.get("id"),
            "email": attrs.get("email", ""),
            "first_name": attrs.get("first_name", ""),
            "last_name": attrs.get("last_name", ""),
            "created": attrs.get("created", ""),
            "subscriptions": attrs.get("subscriptions", {}),
        }

    # ------------------------------------------------------------------
    # Lists
    # ------------------------------------------------------------------

    def list_lists(self) -> dict:
        """Return all lists in the account."""
        resp = self.api.Lists.get_lists()
        lists = resp.get("data", [])
        return {
            "count": len(lists),
            "lists": [
                {
                    "id": l.get("id"),
                    "name": l.get("attributes", {}).get("name", ""),
                    "created": l.get("attributes", {}).get("created", ""),
                    "updated": l.get("attributes", {}).get("updated", ""),
                }
                for l in lists
            ],
        }

    def get_list_profiles(self, list_id: str, page_size: int = 50) -> dict:
        """Return profiles subscribed to a list."""
        resp = self.api.Lists.get_list_profiles(list_id, page_size=page_size)
        profiles = resp.get("data", [])
        return {
            "list_id": list_id,
            "count": len(profiles),
            "profiles": [
                {
                    "id": p.get("id"),
                    "email": p.get("attributes", {}).get("email", ""),
                    "first_name": p.get("attributes", {}).get("first_name", ""),
                }
                for p in profiles
            ],
        }

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    def list_campaigns(self, channel: str = "email") -> dict:
        """Return all campaigns for a given channel (email or sms)."""
        resp = self.api.Campaigns.get_campaigns(
            filter=f"equals(messages.channel,'{channel}')",
        )
        campaigns = resp.get("data", [])
        return {
            "count": len(campaigns),
            "channel": channel,
            "campaigns": [
                {
                    "id": c.get("id"),
                    "name": c.get("attributes", {}).get("name", ""),
                    "status": c.get("attributes", {}).get("status", ""),
                    "send_time": c.get("attributes", {}).get("scheduled_at", ""),
                    "created": c.get("attributes", {}).get("created_at", ""),
                }
                for c in campaigns
            ],
        }

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def list_metrics(self) -> dict:
        """Return all available metrics."""
        resp = self.api.Metrics.get_metrics()
        metrics = resp.get("data", [])
        return {
            "count": len(metrics),
            "metrics": [
                {
                    "id": m.get("id"),
                    "name": m.get("attributes", {}).get("name", ""),
                    "service": m.get("attributes", {}).get("service", ""),
                }
                for m in metrics
            ],
        }

    # ------------------------------------------------------------------
    # Events / Track
    # ------------------------------------------------------------------

    def create_event(self, event_name: str, email: str, properties: dict = None) -> dict:
        """
        Track a custom event for a profile.

        Args:
            event_name:  e.g. "Placed Order", "Viewed Product"
            email:       Profile email
            properties:  Arbitrary event properties dict
        """
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
        """High-level account summary: lists, campaigns, metrics counts."""
        try:
            account = self.get_account()
        except Exception as e:
            account = {"error": str(e)}
        try:
            lists = self.list_lists()
        except Exception as e:
            lists = {"error": str(e)}
        try:
            campaigns = self.list_campaigns()
        except Exception as e:
            campaigns = {"error": str(e)}
        try:
            metrics = self.list_metrics()
        except Exception as e:
            metrics = {"error": str(e)}

        return {
            "account": account,
            "lists_count": lists.get("count", 0),
            "lists": lists.get("lists", []),
            "campaigns_count": campaigns.get("count", 0),
            "recent_campaigns": campaigns.get("campaigns", [])[:5],
            "metrics_count": metrics.get("count", 0),
        }
