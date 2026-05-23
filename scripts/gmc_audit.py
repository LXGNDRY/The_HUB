#!/usr/bin/env python3
"""
gmc_audit.py — Full Merchant Center feed audit
Checks: products, GTINs, disapprovals, feed status, shipping, images
"""
import os, json, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/content"]
)
service = build("content", "v2.1", credentials=creds)
MERCHANT_ID = "582171114"

# ── 1. Account info ──────────────────────────────────────────
print("=" * 70)
print("ACCOUNT")
print("=" * 70)
acct = service.accounts().get(merchantId=MERCHANT_ID, accountId=MERCHANT_ID).execute()
print(f"  Name:        {acct.get('name')}")
print(f"  Website:     {acct.get('websiteUrl')}")
print(f"  Adult:       {acct.get('adultContent', False)}")

# ── 2. Feed status ───────────────────────────────────────────
print("\n" + "=" * 70)
print("DATAFEEDS")
print("=" * 70)
feeds = service.datafeeds().list(merchantId=MERCHANT_ID).execute()
feed_list = feeds.get("resources", [])
if not feed_list:
    print("  No datafeeds found (using Merchant Center auto-sync or manual upload)")
else:
    for f in feed_list:
        print(f"  [{f['id']}] {f.get('name')} — format: {f.get('format',{}).get('fileEncoding','?')}")

# ── 3. Products summary ──────────────────────────────────────
print("\n" + "=" * 70)
print("PRODUCTS SUMMARY")
print("=" * 70)

all_products = []
request = service.products().list(merchantId=MERCHANT_ID, maxResults=250)
while request is not None:
    result = request.execute()
    batch = result.get("resources", [])
    all_products.extend(batch)
    request = service.products().list_next(request, result)

print(f"  Total products in feed: {len(all_products)}")

# ── 4. GTIN audit ────────────────────────────────────────────
print("\n" + "=" * 70)
print("GTIN AUDIT")
print("=" * 70)
missing_gtin = []
has_gtin = []
for p in all_products:
    gtin = p.get("gtin", "").strip()
    title = p.get("title", "")[:60]
    pid = p.get("id", "")
    if not gtin:
        missing_gtin.append((pid, title))
    else:
        has_gtin.append((pid, title, gtin))

print(f"  With GTIN:    {len(has_gtin)}")
print(f"  Missing GTIN: {len(missing_gtin)}")
if missing_gtin:
    print("\n  MISSING GTIN:")
    for pid, title in missing_gtin[:30]:
        print(f"    - {title[:55]}")
    if len(missing_gtin) > 30:
        print(f"    ... and {len(missing_gtin)-30} more")

# ── 5. Disapprovals ──────────────────────────────────────────
print("\n" + "=" * 70)
print("PRODUCT STATUS / DISAPPROVALS")
print("=" * 70)
statuses = service.productstatuses().list(
    merchantId=MERCHANT_ID, maxResults=250
).execute()
status_list = statuses.get("resources", [])

approved = []
disapproved = []
pending = []
issues_summary = {}

for s in status_list:
    title = s.get("title", "")[:55]
    pid = s.get("productId", "")
    dest_statuses = s.get("destinationStatuses", [])
    item_issues = s.get("itemLevelIssues", [])
    
    is_disapproved = any(
        d.get("approvalStatus") == "disapproved" or d.get("status") == "disapproved"
        for d in dest_statuses
    )
    is_pending = any(
        d.get("approvalStatus") == "pending" or d.get("status") == "pending"
        for d in dest_statuses
    )
    
    if is_disapproved:
        disapproved.append((pid, title, item_issues))
    elif is_pending:
        pending.append((pid, title))
    else:
        approved.append((pid, title))
    
    for issue in item_issues:
        code = issue.get("code", "unknown")
        issues_summary[code] = issues_summary.get(code, 0) + 1

print(f"  Approved:    {len(approved)}")
print(f"  Pending:     {len(pending)}")
print(f"  Disapproved: {len(disapproved)}")

if disapproved:
    print("\n  DISAPPROVED PRODUCTS:")
    for pid, title, issues in disapproved[:20]:
        codes = [i.get("code","?") for i in issues]
        print(f"    - {title}")
        print(f"      Issues: {', '.join(codes[:5])}")

if issues_summary:
    print("\n  TOP ISSUE CODES ACROSS ALL PRODUCTS:")
    for code, count in sorted(issues_summary.items(), key=lambda x: -x[1])[:15]:
        print(f"    [{count:3d}x] {code}")

# ── 6. Missing images / descriptions ─────────────────────────
print("\n" + "=" * 70)
print("DATA QUALITY FLAGS")
print("=" * 70)
no_image = [p for p in all_products if not p.get("imageLink","").strip()]
no_desc  = [p for p in all_products if not p.get("description","").strip()]
no_brand = [p for p in all_products if not p.get("brand","").strip()]
no_price = [p for p in all_products if not p.get("price")]
no_mpn   = [p for p in all_products if not p.get("mpn","").strip()]

print(f"  Missing image:       {len(no_image)}")
print(f"  Missing description: {len(no_desc)}")
print(f"  Missing brand:       {len(no_brand)}")
print(f"  Missing price:       {len(no_price)}")
print(f"  Missing MPN:         {len(no_mpn)}")

# ── 7. Shipping settings ─────────────────────────────────────
print("\n" + "=" * 70)
print("SHIPPING SETTINGS")
print("=" * 70)
try:
    shipping = service.shippingsettings().get(
        merchantId=MERCHANT_ID, accountId=MERCHANT_ID
    ).execute()
    services_list = shipping.get("services", [])
    print(f"  Shipping services configured: {len(services_list)}")
    for svc in services_list:
        print(f"    - {svc.get('name')} | active: {svc.get('active')} | countries: {svc.get('deliveryCountries',['?'])}")
except Exception as e:
    print(f"  Could not fetch shipping settings: {e}")

print("\n" + "=" * 70)
print("AUDIT COMPLETE")
print("=" * 70)
