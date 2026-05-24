#!/usr/bin/env python3
"""
gtm_purchase_fix.py — Fix GTM conversion tracking for Legendary Branding

WHAT THIS DOES:
1. Authenticates to GTM API using GSC OAuth user credentials (has tagmanager scope)
2. Lists triggers in workspace 8 to find or create the purchase trigger
3. Creates GA4 - Purchase tag (gaawe, event: purchase) 
4. Creates Google Ads - Purchase tag (awct) with purchase conversion label
5. Creates Google Ads - Purchase User Info tag (awud) for enhanced conversions
6. Publishes workspace 8 as version 22

ACCOUNT:
  Container: GTM-58KH82X
  Account ID: 6111521813  
  Container ID: 122787695
  Workspace: 8

CONVERSION:
  Google Ads Conversion ID: 11216638233
  Purchase conversion label: fetched from env var GOOGLE_ADS_PURCHASE_LABEL
  (If not set, creates tags with placeholder — label must be added manually in Google Ads UI)
"""

import os
import json
import sys
import logging

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("gtm-purchase-fix")

# ── Constants ──────────────────────────────────────────────────────────────
ACCOUNT_ID   = "6111521813"
CONTAINER_ID = "122787695"
WORKSPACE_ID = "8"
PARENT       = f"accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}/workspaces/{WORKSPACE_ID}"

CONV_ID            = "11216638233"
PURCHASE_LABEL_ENV = os.getenv("GOOGLE_ADS_PURCHASE_LABEL", "")  # set via GitHub secret
GA4_ID             = "{{GA4 - Id}}"   # existing variable in workspace

# Existing variable references (confirmed from tag audit)
VAR_VALUE    = "{{Value}}"
VAR_CURRENCY = "{{Currency}}"
VAR_ITEMS    = "{{Ecom Item}}"
VAR_CUST_INFO = "{{Google Ads - Customer Info}}"

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"


# ── Auth ───────────────────────────────────────────────────────────────────
def get_credentials():
    """
    Build OAuth2 credentials from GSC_CLIENT_SECRET_JSON + GSC_TOKEN_JSON.
    These are user-level OAuth credentials with tagmanager scope.
    """
    client_secret_raw = os.environ["GSC_CLIENT_SECRET_JSON"]
    token_raw         = os.environ["GSC_TOKEN_JSON"]
    
    client_info = json.loads(client_secret_raw)
    token_info  = json.loads(token_raw)
    
    # Handle both "installed" and "web" client types
    client_data = client_info.get("installed") or client_info.get("web")
    
    creds = Credentials(
        token=token_info.get("token"),
        refresh_token=token_info.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_data["client_id"],
        client_secret=client_data["client_secret"],
        scopes=token_info.get("scopes", [
            "https://www.googleapis.com/auth/tagmanager.edit.containers",
            "https://www.googleapis.com/auth/tagmanager.publish",
        ]),
    )
    return creds


def get_service(creds):
    return build("tagmanager", "v2", credentials=creds, cache_discovery=False)


# ── Helpers ────────────────────────────────────────────────────────────────
def find_or_create_purchase_trigger(service):
    """
    Look for an existing Custom Event trigger for 'purchase'.
    If not found, create one.
    Returns the trigger ID as a string.
    """
    logger.info("Listing triggers in workspace %s...", WORKSPACE_ID)
    resp = service.accounts().containers().workspaces().triggers().list(
        parent=PARENT
    ).execute()
    
    triggers = resp.get("trigger", [])
    logger.info("Found %d triggers.", len(triggers))
    
    for t in triggers:
        logger.info("  Trigger: %s | type=%s | id=%s", t.get("name"), t.get("type"), t.get("triggerId"))
        # Look for existing purchase custom event trigger
        if t.get("type") == "CUSTOM_EVENT":
            filters = t.get("customEventFilter", [])
            for f in filters:
                for p in f.get("parameter", []):
                    if p.get("key") == "arg1" and "purchase" in str(p.get("value", "")).lower():
                        logger.info("Found existing purchase trigger: %s (id=%s)", t.get("name"), t.get("triggerId"))
                        return t.get("triggerId")
    
    # No purchase trigger found — create one
    logger.info("No purchase trigger found. Creating Custom Event trigger for 'purchase'...")
    
    if DRY_RUN:
        logger.info("[DRY RUN] Would create purchase trigger")
        return "DRY_RUN_TRIGGER_ID"
    
    trigger_body = {
        "name": "CE - purchase",
        "type": "CUSTOM_EVENT",
        "customEventFilter": [
            {
                "type": "EQUALS",
                "parameter": [
                    {"type": "TEMPLATE", "key": "arg0", "value": "{{_event}}"},
                    {"type": "TEMPLATE", "key": "arg1", "value": "purchase"},
                ]
            }
        ]
    }
    
    new_trigger = service.accounts().containers().workspaces().triggers().create(
        parent=PARENT, body=trigger_body
    ).execute()
    
    trigger_id = new_trigger.get("triggerId")
    logger.info("Created purchase trigger: CE - purchase (id=%s)", trigger_id)
    return trigger_id


def tag_exists(service, tag_name):
    """Check if a tag with this name already exists in workspace 8."""
    resp = service.accounts().containers().workspaces().tags().list(
        parent=PARENT
    ).execute()
    for t in resp.get("tag", []):
        if t.get("name") == tag_name:
            logger.info("Tag '%s' already exists (id=%s) — skipping.", tag_name, t.get("tagId"))
            return True
    return False


def create_ga4_purchase_tag(service, trigger_id):
    """Create GA4 - Purchase tag."""
    name = "GA4 - Purchase"
    if tag_exists(service, name):
        return None
    
    body = {
        "name": name,
        "type": "gaawe",
        "parameter": [
            {"type": "boolean", "key": "sendEcommerceData", "value": "false"},
            {"type": "template", "key": "eventName", "value": "purchase"},
            {"type": "template", "key": "measurementIdOverride", "value": GA4_ID},
            {
                "type": "list",
                "key": "eventSettingsTable",
                "list": [
                    {"type": "map", "map": [
                        {"type": "template", "key": "parameter", "value": "transaction_id"},
                        {"type": "template", "key": "parameterValue", "value": "{{Order ID}}"},
                    ]},
                    {"type": "map", "map": [
                        {"type": "template", "key": "parameter", "value": "value"},
                        {"type": "template", "key": "parameterValue", "value": VAR_VALUE},
                    ]},
                    {"type": "map", "map": [
                        {"type": "template", "key": "parameter", "value": "currency"},
                        {"type": "template", "key": "parameterValue", "value": VAR_CURRENCY},
                    ]},
                    {"type": "map", "map": [
                        {"type": "template", "key": "parameter", "value": "items"},
                        {"type": "template", "key": "parameterValue", "value": VAR_ITEMS},
                    ]},
                ]
            }
        ],
        "firingTriggerId": [trigger_id],
        "tagFiringOption": "oncePerEvent",
    }
    
    if DRY_RUN:
        logger.info("[DRY RUN] Would create tag: %s", name)
        return {"tagId": "DRY_RUN", "name": name}
    
    resp = service.accounts().containers().workspaces().tags().create(
        parent=PARENT, body=body
    ).execute()
    logger.info("Created tag: %s (id=%s)", name, resp.get("tagId"))
    return resp


def create_gads_purchase_tag(service, trigger_id, purchase_label):
    """Create Google Ads - Purchase conversion tag."""
    name = "Google Ads - Purchase"
    if tag_exists(service, name):
        return None
    
    if not purchase_label:
        logger.warning("No purchase conversion label provided. Using placeholder.")
        purchase_label = "REPLACE_WITH_PURCHASE_LABEL"
    
    body = {
        "name": name,
        "type": "awct",
        "parameter": [
            {"type": "boolean",  "key": "enableNewCustomerReporting", "value": "false"},
            {"type": "boolean",  "key": "enableConversionLinker",     "value": "true"},
            {"type": "boolean",  "key": "enableProductReporting",     "value": "false"},
            {"type": "template", "key": "conversionValue",            "value": VAR_VALUE},
            {"type": "boolean",  "key": "enableShippingData",         "value": "false"},
            {"type": "template", "key": "conversionId",               "value": CONV_ID},
            {"type": "template", "key": "currencyCode",               "value": VAR_CURRENCY},
            {"type": "template", "key": "conversionLabel",            "value": purchase_label},
            {"type": "boolean",  "key": "rdp",                        "value": "false"},
        ],
        "firingTriggerId": [trigger_id],
        "tagFiringOption": "oncePerLoad",
    }
    
    if DRY_RUN:
        logger.info("[DRY RUN] Would create tag: %s with label=%s", name, purchase_label)
        return {"tagId": "DRY_RUN", "name": name}
    
    resp = service.accounts().containers().workspaces().tags().create(
        parent=PARENT, body=body
    ).execute()
    logger.info("Created tag: %s (id=%s)", name, resp.get("tagId"))
    return resp


def create_gads_purchase_user_info_tag(service, trigger_id):
    """Create Google Ads - Purchase User Info tag (enhanced conversions)."""
    name = "Google Ads - Purchase - User Info"
    if tag_exists(service, name):
        return None
    
    body = {
        "name": name,
        "type": "awud",
        "parameter": [
            {"type": "template", "key": "userDataVariable", "value": VAR_CUST_INFO},
            {"type": "boolean",  "key": "enableConversionLinker", "value": "true"},
            {"type": "template", "key": "conversionId",           "value": CONV_ID},
        ],
        "firingTriggerId": [trigger_id],
        "tagFiringOption": "oncePerEvent",
    }
    
    if DRY_RUN:
        logger.info("[DRY RUN] Would create tag: %s", name)
        return {"tagId": "DRY_RUN", "name": name}
    
    resp = service.accounts().containers().workspaces().tags().create(
        parent=PARENT, body=body
    ).execute()
    logger.info("Created tag: %s (id=%s)", name, resp.get("tagId"))
    return resp


def publish_workspace(service, version_name, notes):
    """Create version from workspace 8 and publish it."""
    logger.info("Creating version: %s", version_name)
    
    if DRY_RUN:
        logger.info("[DRY RUN] Would publish workspace as: %s", version_name)
        return {"containerVersion": {"containerVersionId": "DRY_RUN"}}
    
    # Create version
    version_resp = service.accounts().containers().workspaces().create_version(
        path=PARENT,
        body={"name": version_name, "notes": notes}
    ).execute()
    
    version_id = version_resp.get("containerVersion", {}).get("containerVersionId")
    logger.info("Version created: %s", version_id)
    
    # Publish it
    container_path = f"accounts/{ACCOUNT_ID}/containers/{CONTAINER_ID}"
    publish_resp = service.accounts().containers().versions().publish(
        path=f"{container_path}/versions/{version_id}"
    ).execute()
    
    logger.info("Version %s published live.", version_id)
    return {"version_id": version_id, "publish_status": publish_resp}


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    logger.info("=== GTM Purchase Tracking Fix ===")
    logger.info("Container: GTM-58KH82X | Workspace: %s | DRY_RUN=%s", WORKSPACE_ID, DRY_RUN)
    
    # Get the purchase conversion label from env
    purchase_label = PURCHASE_LABEL_ENV
    if not purchase_label:
        logger.warning("GOOGLE_ADS_PURCHASE_LABEL not set — will query Google Ads API")
        # We'll use a placeholder; the label must be obtained from Google Ads UI
        # Tools > Conversions > Purchase > Tag setup > Global site tag (gtag.js)
        # The label is in the snippet: gtag('event', 'conversion', {'send_to': 'AW-11216638233/LABEL'})
        purchase_label = ""
    
    logger.info("Purchase conversion label: %s", purchase_label or "(not set — placeholder will be used)")
    
    # Authenticate
    try:
        creds = get_credentials()
        service = get_service(creds)
        logger.info("Authenticated to GTM API.")
    except Exception as e:
        logger.error("Auth failed: %s", e)
        sys.exit(1)
    
    # Step 1: Find or create purchase trigger
    try:
        trigger_id = find_or_create_purchase_trigger(service)
        logger.info("Purchase trigger ID: %s", trigger_id)
    except HttpError as e:
        logger.error("Failed to get/create trigger: %s", e)
        sys.exit(1)
    
    # Step 2: Create GA4 - Purchase tag
    try:
        create_ga4_purchase_tag(service, trigger_id)
    except HttpError as e:
        logger.error("Failed to create GA4 Purchase tag: %s", e)
        sys.exit(1)
    
    # Step 3: Create Google Ads - Purchase tag
    try:
        create_gads_purchase_tag(service, trigger_id, purchase_label)
    except HttpError as e:
        logger.error("Failed to create Google Ads Purchase tag: %s", e)
        sys.exit(1)
    
    # Step 4: Create Google Ads - Purchase User Info tag
    try:
        create_gads_purchase_user_info_tag(service, trigger_id)
    except HttpError as e:
        logger.error("Failed to create Purchase User Info tag: %s", e)
        sys.exit(1)
    
    # Step 5: Publish
    if not DRY_RUN:
        try:
            result = publish_workspace(
                service,
                version_name="Version 22 — Purchase Conversion Fix",
                notes=(
                    "Added: CE - purchase trigger, GA4 - Purchase tag, "
                    "Google Ads - Purchase tag, Google Ads - Purchase User Info tag. "
                    "Fixes conversion tracking misconfiguration (micro-events counted as purchases)."
                )
            )
            logger.info("Published: version %s", result.get("version_id"))
        except HttpError as e:
            logger.error("Publish failed: %s", e)
            sys.exit(1)
    
    logger.info("=== Done ===")
    if not purchase_label:
        logger.warning("IMPORTANT: GOOGLE_ADS_PURCHASE_LABEL was not set.")
        logger.warning("The Google Ads - Purchase tag was created with a placeholder label.")
        logger.warning("You must update the conversion label in Google Ads:")
        logger.warning("  Go to: Tools > Conversions > find 'Purchase' action")
        logger.warning("  Get the label from: Tag setup > Use Google Tag Manager > Conversion label")
        logger.warning("  Then update tag 'Google Ads - Purchase' in GTM workspace 8")


if __name__ == "__main__":
    main()
