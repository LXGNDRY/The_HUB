#!/usr/bin/env python3
import os, json, time
from google.oauth2 import service_account
from googleapiclient.discovery import build

MERCHANT_ID = "582171114"
SA_KEY_JSON = os.environ["GCP_SA_KEY"]

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds, cache_discovery=False)

print("=== datafeeds.list ===")
result = service.datafeeds().list(merchantId=MERCHANT_ID).execute()
feeds = result.get("resources", [])
print(f"Total datafeeds: {len(feeds)}")
for f in feeds[:5]:
    print(json.dumps({k: f.get(k) for k in ["id","name","format","targets","attributeRules"]}, indent=2))

print("\n=== accounts.list (subaccounts check) ===")
try:
    acc = service.accounts().get(merchantId=MERCHANT_ID, accountId=MERCHANT_ID).execute()
    print(json.dumps({k: acc.get(k) for k in ["id","name","kind","websiteUrl"]}, indent=2))
except Exception as e:
    print(f"Error: {e}")

# Try the newer Content API datasources endpoint
print("\n=== Attempting datasources via requests (v1 API) ===")
import google.auth.transport.requests
import requests as req_lib
auth_req = google.auth.transport.requests.Request()
creds.refresh(auth_req)
token = creds.token

url = f"https://merchantapi.googleapis.com/datasources/v1beta/accounts/{MERCHANT_ID}/dataSources"
headers = {"Authorization": f"Bearer {token}"}
resp = req_lib.get(url, headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    sources = data.get("dataSources", [])
    print(f"Total data sources: {len(sources)}")
    for s in sources[:10]:
        print(json.dumps({k: s.get(k) for k in ["name","displayName","dataSourceId","primaryProductDataSource","supplementalProductDataSource","fileInput","merchantReviewDataSource"]}, indent=2))
else:
    print(resp.text[:500])
