#!/usr/bin/env python3
import os, json, sys
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

SITE_URL = "https://legendary-branding.com/"
SCOPES = ["https://www.googleapis.com/auth/webmasters"]

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    print("ERROR: GCP_SA_KEY not set", file=sys.stderr)
    sys.exit(1)

sa_info = json.loads(SA_KEY_JSON)
print(f"Service account email: {sa_info.get('client_email')}")
print(f"Project ID: {sa_info.get('project_id')}")

creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
creds.refresh(GoogleRequest())
print(f"Token acquired: {creds.token[:30]}...")
print(f"Token valid: {creds.valid}")

# Test 1: List GSC sites this SA can see
resp = requests.get(
    "https://www.googleapis.com/webmasters/v3/sites",
    headers={"Authorization": f"Bearer {creds.token}"}
)
print(f"\n--- GSC Sites list (status {resp.status_code}) ---")
print(json.dumps(resp.json(), indent=2))

# Test 2: Try URL inspection on one URL
payload = {
    "inspectionUrl": "https://legendary-branding.com/products/butterfly-tee",
    "siteUrl": SITE_URL
}
resp2 = requests.post(
    "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
    headers={"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"},
    json=payload
)
print(f"\n--- URL Inspection (status {resp2.status_code}) ---")
print(json.dumps(resp2.json(), indent=2))
