import os, json, sys, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest

SA_KEY = os.environ["GCP_SA_KEY"]
CUSTOMER_ID = "1137623123"
CAMPAIGN_ID = "23907560337"

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY),
    scopes=["https://www.googleapis.com/auth/adwords"],
)
creds.refresh(GoogleRequest())

# Try without dev token first — read-only calls sometimes work without it
headers = {
    "Authorization": f"Bearer {creds.token}",
    "Content-Type": "application/json",
}

# Also check if GOOGLE_ADS_DEVELOPER_TOKEN exists
dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "")
if dev_token:
    headers["developer-token"] = dev_token
    print("Using GOOGLE_ADS_DEVELOPER_TOKEN")
else:
    print("WARNING: No GOOGLE_ADS_DEVELOPER_TOKEN found - request may fail")

query = f"""
SELECT
  asset_group.id,
  asset_group.name,
  asset_group.status,
  asset_group.primary_status,
  asset_group.primary_status_reasons,
  asset_group.final_urls
FROM asset_group
WHERE asset_group.campaign = 'customers/{CUSTOMER_ID}/campaigns/{CAMPAIGN_ID}'
"""

url = f"https://googleads.googleapis.com/v21/customers/{CUSTOMER_ID}/googleAds:search"
r = requests.post(url, headers=headers, json={"query": query})
print(f"Status: {r.status_code}")
data = r.json()
if "results" in data:
    print(f"Asset groups found: {len(data['results'])}")
    for ag in data["results"]:
        print(json.dumps(ag, indent=2))
else:
    print(json.dumps(data, indent=2))
