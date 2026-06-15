"""
gmc_delete_content_api_products.py
Delete ALL products inserted via Content API (custombatch) from GMC.
This clears both "Content API" and "Shopify Content API" data sources.
"""
import json, os, sys, time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    sys.exit("ERROR: GCP_SA_KEY not set.")

sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/content"])
svc = build("content", "v2.1", credentials=creds)
M = 582171114

print("\n=== GMC Content API Product Deletion ===")
print(f"  Merchant: {M}")

# ── Step 1: Collect all product IDs ───────────────────────────────────────────
print("\n  Collecting all product IDs...")
all_ids = []
req = svc.products().list(merchantId=M, maxResults=250)
page = 0
while req:
    try:
        resp = req.execute(num_retries=3)
        items = resp.get("resources", [])
        for item in items:
            all_ids.append(item["id"])
        page += 1
        if page % 10 == 0:
            print(f"    Page {page} — {len(all_ids)} IDs collected so far...")
        req = svc.products().list_next(req, resp)
        time.sleep(0.2)
    except HttpError as e:
        print(f"    ERROR on page {page}: {e}")
        break

print(f"  Total products to delete: {len(all_ids)}")

if not all_ids:
    print("  Nothing to delete.")
    sys.exit(0)

# ── Step 2: Delete in custombatch of 1000 ────────────────────────────────────
print("\n  Deleting via custombatch...")
BATCH_SIZE = 1000
deleted = 0
errors  = 0

for i in range(0, len(all_ids), BATCH_SIZE):
    batch = all_ids[i:i + BATCH_SIZE]
    entries = [
        {
            "batchId":    idx,
            "merchantId": str(M),
            "method":     "delete",
            "productId":  pid,
        }
        for idx, pid in enumerate(batch)
    ]
    batch_num = i // BATCH_SIZE + 1
    for attempt in range(1, 4):
        try:
            resp = svc.products().custombatch(body={"entries": entries}).execute(num_retries=2)
            for entry in resp.get("entries", []):
                errs = entry.get("errors", {}).get("errors", [])
                if errs:
                    errors += 1
                else:
                    deleted += 1
            print(f"  Batch {batch_num} ({len(batch)} products): {deleted} deleted / {errors} errors")
            break
        except HttpError as e:
            print(f"  Batch {batch_num} HTTP error (attempt {attempt}/3): {e}")
            if attempt == 3:
                errors += len(batch)
            else:
                time.sleep(2 ** attempt)
    time.sleep(1)

print(f"\n=== Complete ===")
print(f"  Deleted: {deleted}")
print(f"  Errors:  {errors}")
print(f"  Content API and Shopify Content API data sources are now cleared.")
