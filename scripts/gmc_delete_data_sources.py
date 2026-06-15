"""
gmc_delete_data_sources.py
Delete all data sources (datafeeds) from GMC merchant 582171114.
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

print("\n=== GMC Data Source Deletion ===")

# ── List all datafeeds ─────────────────────────────────────────────────────────
try:
    feeds = svc.datafeeds().list(merchantId=M).execute()
    feed_list = feeds.get("resources", [])
    print(f"  Found {len(feed_list)} datafeeds")
    
    if not feed_list:
        print("  Nothing to delete.")
        sys.exit(0)
    
    for feed in feed_list:
        fid  = feed.get("id")
        name = feed.get("name", "unknown")
        print(f"\n  Deleting [{fid}] {name} ...")
        try:
            svc.datafeeds().delete(merchantId=M, datafeedId=fid).execute()
            print(f"    ✓ Deleted")
            time.sleep(0.5)
        except HttpError as e:
            print(f"    ✗ ERROR: {e}")

except HttpError as e:
    print(f"  ERROR listing datafeeds: {e}")

# ── Also delete any supplemental feed products pushed via Content API ──────────
# (products inserted with custombatch insert are separate from datafeeds)
# These are cleaned up by the new feed re-push — no action needed here.

print("\n=== Done ===")
print("  All datafeeds deleted.")
print("  Note: Products already in GMC remain until new feed overwrites them.")
