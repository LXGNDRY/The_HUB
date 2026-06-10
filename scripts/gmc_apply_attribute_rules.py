#!/usr/bin/env python3
"""
gmc_apply_attribute_rules.py — Legendary Branding
Apply standard apparel attribute rules to all GMC data sources
that have products but are missing rules:
  - age_group → adult
  - gender    → unisex
  - identifier_exists → false

Uses the datafeeds.update() endpoint to patch attribute rules per feed.
"""
import os, json, time
from google.oauth2 import service_account
from googleapiclient.discovery import build

MERCHANT_ID = "582171114"
SA_KEY_JSON = os.environ["GCP_SA_KEY"]

# Standard apparel attribute rules to apply
STANDARD_RULES = [
    {
        "attributeName": "ageGroup",
        "attributeValue": "adult",
    },
    {
        "attributeName": "gender",
        "attributeValue": "unisex",
    },
    {
        "attributeName": "identifierExists",
        "attributeValue": "false",
    },
]

creds = service_account.Credentials.from_service_account_info(
    json.loads(SA_KEY_JSON),
    scopes=["https://www.googleapis.com/auth/content"],
)
service = build("content", "v2.1", credentials=creds, cache_discovery=False)

print("=" * 60)
print("GMC ATTRIBUTE RULES — Apply to all feeds with products")
print("=" * 60)

# Step 1: List all feeds
print("\nFetching data sources...")
for attempt in range(4):
    try:
        result = service.datafeeds().list(merchantId=MERCHANT_ID).execute()
        feeds = result.get("resources", [])
        print(f"  Found {len(feeds)} total data sources")
        break
    except Exception as e:
        print(f"  Attempt {attempt+1} failed: {e}")
        if attempt < 3:
            time.sleep(15)
        else:
            raise

# Step 2: Identify feeds with products
print("\nChecking product counts per feed...")
feeds_with_products = []
for f in feeds:
    fid  = str(f.get("id", ""))
    name = f.get("name", "")
    targets = f.get("targets", [{}])
    country = targets[0].get("country", "-") if targets else "-"
    lang    = targets[0].get("language", "-") if targets else "-"
    try:
        st    = service.datafeedstatuses().get(merchantId=MERCHANT_ID, datafeedId=fid).execute()
        items = st.get("itemsTotal", 0)
    except Exception as e:
        items = 0
    time.sleep(0.3)

    if items and int(items) > 0:
        feeds_with_products.append({
            "id": fid, "name": name,
            "country": country, "lang": lang, "items": items,
            "raw": f
        })
        print(f"  HAS PRODUCTS → id={fid} | {name} | {country}/{lang} | {items} items")
    else:
        print(f"  empty        → id={fid} | {name} | {country}/{lang}")

print(f"\n{len(feeds_with_products)} feeds with products found")

# Step 3: Apply attribute rules to each feed with products
print("\n" + "=" * 60)
print("Applying attribute rules...")
print("=" * 60)

applied = 0
skipped = 0
failed  = 0

for feed_info in feeds_with_products:
    fid  = feed_info["id"]
    name = feed_info["name"]
    country = feed_info["country"]
    raw  = feed_info["raw"]

    # Check existing attribute rules on the feed
    existing_rules = raw.get("attributeRules", [])
    existing_attrs = {r.get("attributeName") for r in existing_rules}

    # Determine which rules are missing
    needed = [
        r for r in STANDARD_RULES
        if r["attributeName"] not in existing_attrs
    ]

    if not needed:
        print(f"  SKIP (already has all rules) → {name} | {country}")
        skipped += 1
        continue

    print(f"  APPLYING → {name} | {country} | adding: {[r['attributeName'] for r in needed]}")

    # Merge existing + needed rules
    updated_rules = existing_rules + needed

    # Build minimal patch body
    patch_body = dict(raw)
    patch_body["attributeRules"] = updated_rules

    for attempt in range(3):
        try:
            service.datafeeds().update(
                merchantId=MERCHANT_ID,
                datafeedId=fid,
                body=patch_body
            ).execute()
            print(f"    ✓ Rules applied to {name} ({country})")
            applied += 1
            time.sleep(0.5)
            break
        except Exception as e:
            print(f"    Attempt {attempt+1} error: {e}")
            if attempt < 2:
                time.sleep(10)
            else:
                print(f"    ✗ FAILED for {name}")
                failed += 1

print("\n" + "=" * 60)
print("COMPLETE")
print(f"  Applied : {applied}")
print(f"  Skipped : {skipped} (already configured)")
print(f"  Failed  : {failed}")
print("=" * 60)
