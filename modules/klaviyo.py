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
  - Flows (list, get messages, get templates)
  - Templates (list, get, create, assign to flow message)

Requires: KLAVIYO_API_KEY env var (private API key starting with pk_)
Uses Klaviyo REST API v2024-10-15 directly for flows/templates
(SDK v10 used for profiles/lists/campaigns/metrics).
"""

import os
import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger("gcp-bot.klaviyo")

KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")
KLAVIYO_API_REV = "2024-10-15"
KLAVIYO_BASE    = "https://a.klaviyo.com/api"


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


def _headers() -> dict:
    if not KLAVIYO_API_KEY:
        raise RuntimeError("KLAVIYO_API_KEY is not set")
    return {
        "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
        "revision": KLAVIYO_API_REV,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _get(path: str, params: dict = None) -> dict:
    url = f"{KLAVIYO_BASE}/{path.lstrip('/')}"
    resp = requests.get(url, headers=_headers(), params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _patch(path: str, body: dict) -> dict:
    url = f"{KLAVIYO_BASE}/{path.lstrip('/')}"
    resp = requests.patch(url, headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json() if resp.text else {"status": "ok"}


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

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------

    def list_flows(self, page_size: int = 50) -> dict:
        """List all flows with their IDs, names, statuses, and trigger types."""
        data = _get("flows", params={"page[size]": page_size})
        flows = data.get("data", [])
        return {
            "count": len(flows),
            "flows": [
                {
                    "id": f["id"],
                    "name": f["attributes"]["name"],
                    "status": f["attributes"]["status"],
                    "trigger_type": f["attributes"].get("trigger_type"),
                    "created": f["attributes"].get("created"),
                    "updated": f["attributes"].get("updated"),
                }
                for f in flows
            ],
        }

    def get_flow_actions(self, flow_id: str) -> dict:
        """Get all action steps (email/SMS messages) within a flow."""
        data = _get(f"flows/{flow_id}/flow-actions", params={"page[size]": 50})
        actions = data.get("data", [])
        return {
            "flow_id": flow_id,
            "count": len(actions),
            "actions": [
                {
                    "id": a["id"],
                    "action_type": a["attributes"].get("action_type"),
                    "status": a["attributes"].get("status"),
                    "created": a["attributes"].get("created"),
                    "updated": a["attributes"].get("updated"),
                }
                for a in actions
            ],
        }

    def get_flow_messages(self, flow_action_id: str) -> dict:
        """Get all messages (with template IDs) for a flow action."""
        data = _get(f"flow-actions/{flow_action_id}/flow-messages", params={"page[size]": 50})
        messages = data.get("data", [])
        return {
            "flow_action_id": flow_action_id,
            "count": len(messages),
            "messages": [
                {
                    "id": m["id"],
                    "label": m["attributes"].get("label"),
                    "channel": m["attributes"].get("channel"),
                    "template_id": (
                        m.get("relationships", {})
                         .get("template", {})
                         .get("data", {})
                         .get("id")
                    ),
                    "created": m["attributes"].get("created"),
                    "updated": m["attributes"].get("updated"),
                }
                for m in messages
            ],
        }

    def get_flow_message(self, message_id: str) -> dict:
        """Get a single flow message including its template relationship."""
        data = _get(
            f"flow-messages/{message_id}",
            params={"include": "template"}
        )
        m = data.get("data", {})
        return {
            "id": m.get("id"),
            "label": m.get("attributes", {}).get("label"),
            "channel": m.get("attributes", {}).get("channel"),
            "template_id": (
                m.get("relationships", {})
                 .get("template", {})
                 .get("data", {})
                 .get("id")
            ),
        }

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def list_templates(self, page_size: int = 50) -> dict:
        """List all email templates in the account."""
        data = _get("templates", params={"page[size]": page_size, "sort": "-updated"})
        templates = data.get("data", [])
        return {
            "count": len(templates),
            "templates": [
                {
                    "id": t["id"],
                    "name": t["attributes"]["name"],
                    "editor_type": t["attributes"].get("editor_type"),
                    "created": t["attributes"].get("created"),
                    "updated": t["attributes"].get("updated"),
                }
                for t in templates
            ],
        }

    def get_template(self, template_id: str) -> dict:
        """Get a single template by ID."""
        data = _get(f"templates/{template_id}")
        t = data.get("data", {})
        return {
            "id": t.get("id"),
            "name": t.get("attributes", {}).get("name"),
            "editor_type": t.get("attributes", {}).get("editor_type"),
            "html": t.get("attributes", {}).get("html"),
            "created": t.get("attributes", {}).get("created"),
            "updated": t.get("attributes", {}).get("updated"),
        }

    # ------------------------------------------------------------------
    # Assign template to flow message
    # ------------------------------------------------------------------

    def get_template_id_for_flow_message(self, message_id: str) -> str | None:
        """
        Returns the template ID currently linked to a flow message.
        Uses the relationships/template endpoint.
        """
        try:
            data = _get(f"flow-messages/{message_id}/relationships/template")
            return data.get("data", {}).get("id")
        except Exception:
            # Fallback: include template in the message fetch
            data = _get(f"flow-messages/{message_id}", params={"include": "template"})
            return (
                data.get("data", {})
                    .get("relationships", {})
                    .get("template", {})
                    .get("data", {})
                    .get("id")
            )

    def update_template_html(self, template_id: str, name: str, html: str) -> dict:
        """
        Update an existing template's HTML via PATCH /api/templates/{id}.
        This is the supported way to change the content of a flow message's template.
        """
        body = {
            "data": {
                "type": "template",
                "id": template_id,
                "attributes": {
                    "name": name,
                    "html": html,
                }
            }
        }
        result = _patch(f"templates/{template_id}", body)
        return {
            "status": "updated",
            "template_id": template_id,
            "name": name,
        }

    # ------------------------------------------------------------------
    # Bulk: assign all LB templates to their flows
    # ------------------------------------------------------------------

    def assign_lb_templates(self) -> dict:
        """
        Update the HTML of each flow message's existing linked template with
        the new Legendary Branding branded design.

        Strategy (correct Klaviyo API approach):
          1. For each flow message ID (discovered from the flow action traversal)
          2. GET the template ID linked to that message via relationships/template
          3. PATCH /api/templates/{template_id} with the new branded HTML

        Flow → Message → New HTML mapping (message IDs discovered May 2026):
          RgxHfC (Welcome Series)      msg: UjfrVL → LB — Welcome Series Email 1
          RJEsWE (Thank You)           msg: VjwdXC → LB — Customer Thank You
          UL3cRZ (Abandoned Cart)      msg: YkSXSX → LB — Abandoned Cart
          Uujc9V (Browse Abandonment)  msg: Y5aXaT → LB — Browse Abandonment
          WL8kad (Shipping Conf)       msg: YyydEG → LB — Shipping Confirmation
          W97hxA (Out for Delivery)    msg: XVxb45 → LB — Out for Delivery
          Vw6eUX (Delivered+Review)    msg: Ridrhn → LB — Delivered + Review
        """
        import os

        TEMPLATE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "klaviyo_templates", "output"
        )

        # message_id → (flow_name, html_filename, lb_template_name)
        MESSAGE_MAP = {
            "UjfrVL": ("Email Welcome Series",      "lb_welcome_series_email_1.html", "LB — Welcome Series Email 1"),
            "VjwdXC": ("Customer Thank You",          "lb_customer_thank_you.html",     "LB — Customer Thank You"),
            "YkSXSX": ("Abandoned Cart Reminder",    "lb_abandoned_cart.html",         "LB — Abandoned Cart"),
            "Y5aXaT": ("Browse Abandonment",         "lb_browse_abandonment.html",     "LB — Browse Abandonment"),
            "YyydEG": ("LB — Shipping Confirmation", "lb_shipping_confirmation.html",  "LB — Shipping Confirmation"),
            "XVxb45": ("LB — Out for Delivery",      "lb_out_for_delivery.html",       "LB — Out for Delivery"),
            "Ridrhn": ("LB — Delivered + Review",    "lb_delivered_+_review.html",     "LB — Delivered + Review"),
        }

        results = []
        errors  = []

        for message_id, (flow_name, html_file, lb_name) in MESSAGE_MAP.items():
            try:
                # 1. Load branded HTML
                html_path = os.path.join(TEMPLATE_DIR, html_file)
                with open(html_path) as f:
                    branded_html = f.read()

                # 2. Get the existing template ID linked to this flow message
                existing_template_id = self.get_template_id_for_flow_message(message_id)
                if not existing_template_id:
                    errors.append({
                        "message_id": message_id,
                        "flow_name": flow_name,
                        "error": "Could not resolve existing template ID for flow message",
                    })
                    continue

                # 3. Update the existing template's HTML with branded design
                update_result = self.update_template_html(
                    template_id=existing_template_id,
                    name=lb_name,
                    html=branded_html,
                )

                results.append({
                    "flow_name": flow_name,
                    "message_id": message_id,
                    "existing_template_id": existing_template_id,
                    "new_name": lb_name,
                    "status": update_result.get("status"),
                })
                logger.info("Updated template %s for flow '%s'", existing_template_id, flow_name)

            except Exception as e:
                logger.error("assign_lb_templates error for message %s (%s): %s", message_id, flow_name, e)
                errors.append({
                    "message_id": message_id,
                    "flow_name": flow_name,
                    "error": str(e),
                })

        return {
            "updated": len(results),
            "errors": len(errors),
            "results": results,
            "error_details": errors,
        }
