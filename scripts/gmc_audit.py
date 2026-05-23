#!/usr/bin/env python3
"""
gmc_audit.py
Pulls all products from Google Merchant Center via Content API.
Reports: feed status, disapprovals, missing GTINs, image issues.
Uses GCP_SA_KEY service account (must have GMC Admin access).
"""
import os, json, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    print("ERROR: GCP_SA_KEY not set", file=sys.stderr)
    sys.exit(1)

sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info,
    scopes=["https://www.googleapis.com/auth/content"]
)

service = build("content", "v2.1", credentials=creds)

# ── 1. Get merchant accounts ─────────────────────────────────
print("=" * 70)
print("STEP 1: MERCHANT ACCOUNTS")
print("=" * 70)
accounts = service.accounts().authinfo().execute()
print(json.dumps(accounts, indent=2))

