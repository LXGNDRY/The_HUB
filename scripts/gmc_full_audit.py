"""
gmc_full_audit.py — Full GMC account audit
Covers: account info, product statuses, shipping, tax, ads link, data sources
"""
import json, os, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
if not SA_KEY_JSON:
    sys.exit("ERROR: GCP_SA_KEY not set.")
sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/content"])
svc = build("content", "v2.1", credentials=creds)
M = 582171114

results = {}

# ── 1. Account info ──────────────────────────────────────────────────────────
print("\n=== 1. ACCOUNT INFO ===")
try:
    acct = svc.accounts().get(merchantId=M, accountId=M).execute()
    results["account"] = {
        "name": acct.get("name"),
        "websiteUrl": acct.get("websiteUrl"),
        "adultContent": acct.get("adultContent", False),
        "users": len(acct.get("users", [])),
    }
    print(f"  Name:       {acct.get('name')}")
    print(f"  Website:    {acct.get('websiteUrl')}")
    print(f"  Adult:      {acct.get('adultContent', False)}")
except Exception as e:
    results["account"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 2. Account status (verification, claims, issues) ─────────────────────────
print("\n=== 2. ACCOUNT STATUS ===")
try:
    status = svc.accountstatuses().get(merchantId=M, accountId=M).execute()
    issues = status.get("accountLevelIssues", [])
    results["account_status"] = {
        "website_claimed": status.get("websiteClaimed"),
        "issues_count": len(issues),
        "issues": [{"id": i.get("id"), "title": i.get("title"), "severity": i.get("severity"), "documentation": i.get("documentation")} for i in issues],
    }
    print(f"  Website claimed: {status.get('websiteClaimed')}")
    print(f"  Account-level issues: {len(issues)}")
    for issue in issues:
        print(f"    [{issue.get('severity','?')}] {issue.get('title')} — {issue.get('id')}")
except Exception as e:
    results["account_status"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 3. Product statuses summary ───────────────────────────────────────────────
print("\n=== 3. PRODUCT STATUSES ===")
try:
    approved = disapproved = warnings = pending = 0
    disapproved_items = []
    warning_items = []
    req = svc.productstatuses().list(merchantId=M, maxResults=250)
    while req:
        resp = req.execute(num_retries=3)
        for item in resp.get("resources", []):
            dest_statuses = item.get("destinationStatuses", [])
            shopping_status = next(
                (d for d in dest_statuses if d.get("destination") == "Shopping"), None)
            if shopping_status:
                s = shopping_status.get("status", "")
                if s == "approved":
                    approved += 1
                elif s == "disapproved":
                    disapproved += 1
                    disapproved_items.append({
                        "id": item.get("productId"),
                        "title": item.get("title"),
                        "issues": [{"code": iss.get("code"), "description": iss.get("description"), "servability": iss.get("servability")} 
                                   for iss in item.get("itemLevelIssues", []) if iss.get("destination") == "Shopping"]
                    })
                elif s == "pending":
                    pending += 1
                else:
                    warnings += 1
            # Check for item-level issues (warnings even on approved)
            item_issues = [i for i in item.get("itemLevelIssues", []) 
                          if i.get("destination") == "Shopping" and i.get("servability") != "disapproved"]
            if item_issues and shopping_status and shopping_status.get("status") == "approved":
                warnings += 1
                warning_items.append({
                    "id": item.get("productId"),
                    "title": item.get("title"),
                    "issues": [i.get("description") for i in item_issues[:3]]
                })
        req = svc.productstatuses().list_next(req, resp)
    
    total = approved + disapproved + warnings + pending
    results["products"] = {
        "total": total,
        "approved": approved,
        "disapproved": disapproved,
        "warnings": warnings,
        "pending": pending,
        "disapproved_sample": disapproved_items[:5],
        "warning_sample": warning_items[:5],
    }
    print(f"  Total:       {total}")
    print(f"  Approved:    {approved}")
    print(f"  Disapproved: {disapproved}")
    print(f"  Warnings:    {warnings}")
    print(f"  Pending:     {pending}")
    if disapproved_items:
        print(f"\n  DISAPPROVED SAMPLE:")
        for p in disapproved_items[:5]:
            print(f"    {p['title']}")
            for iss in p['issues'][:2]:
                print(f"      → {iss['description']} ({iss['code']})")
    if warning_items:
        print(f"\n  WARNING SAMPLE:")
        for p in warning_items[:3]:
            print(f"    {p['title']}: {p['issues']}")
except Exception as e:
    results["products"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 4. Shipping summary ───────────────────────────────────────────────────────
print("\n=== 4. SHIPPING ===")
try:
    shipping = svc.shippingsettings().get(merchantId=M, accountId=M).execute()
    svcs = shipping.get("services", [])
    countries_covered = {s.get("deliveryCountry") for s in svcs}
    free_countries = {s.get("deliveryCountry") for s in svcs 
                      if s.get("rateGroups",[{}])[0].get("singleValue",{}).get("flatRate",{}).get("value") == "0"}
    
    ad_targets = {'US','GB','CA','FR','DE','IE','ES','IT','AU','NZ','JP','KR','SG','HK','NL','BE','CH','NO','SE','DK','FI','AT','PT','GR','CZ','PL','HU','RO','AE','QA','KW','BH','SA','IL','MX','AR','CL','CO','EC','PE','DO','SV','GT','JM','PA','PR','TT','KZ','AM','GE','MA','EG','JO','LB','ZA','MY'}
    missing_from_ad_targets = ad_targets - countries_covered
    
    results["shipping"] = {
        "total_services": len(svcs),
        "countries_covered": len(countries_covered),
        "free_shipping_countries": len(free_countries),
        "ad_targets_missing_shipping": sorted(missing_from_ad_targets),
    }
    print(f"  Services: {len(svcs)}")
    print(f"  Countries covered: {len(countries_covered)}")
    print(f"  With free shipping: {len(free_countries)}")
    print(f"  Ad targets missing shipping: {sorted(missing_from_ad_targets) or 'None ✓'}")
except Exception as e:
    results["shipping"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 5. Tax settings ───────────────────────────────────────────────────────────
print("\n=== 5. TAX ===")
try:
    tax = svc.liasettings().get(merchantId=M, accountId=M).execute()
    country_settings = tax.get("countrySettings", [])
    results["tax"] = {
        "countries_configured": len(country_settings),
        "countries": [{"country": c.get("country"), "inventory": c.get("inventory", {}).get("status"), "about": c.get("about", {}).get("status")} for c in country_settings]
    }
    print(f"  LIA/Tax countries configured: {len(country_settings)}")
    for c in country_settings:
        print(f"    {c.get('country')}: inventory={c.get('inventory',{}).get('status')} about={c.get('about',{}).get('status')}")
except Exception as e:
    # Try via accounttax
    try:
        tax2 = svc.accounttax().get(merchantId=M, accountId=M).execute()
        rules = tax2.get("rules", [])
        results["tax"] = {"rules": len(rules), "rules_detail": rules[:5]}
        print(f"  Tax rules: {len(rules)}")
        for r in rules[:5]:
            print(f"    {r}")
    except Exception as e2:
        results["tax"] = {"error": str(e2)}
        print(f"  ERROR: {e2}")

# ── 6. Google Ads link ────────────────────────────────────────────────────────
print("\n=== 6. GOOGLE ADS LINK ===")
try:
    ads_links = svc.accounts().get(merchantId=M, accountId=M).execute().get("adsLinks", [])
    results["ads_links"] = ads_links
    if ads_links:
        for link in ads_links:
            print(f"  AdsID: {link.get('adsId')} | Status: {link.get('status')}")
    else:
        print("  No Ads links found")
except Exception as e:
    results["ads_links"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 7. Data sources / feeds ───────────────────────────────────────────────────
print("\n=== 7. DATA SOURCES / FEEDS ===")
try:
    feeds = svc.datafeeds().list(merchantId=M).execute()
    feed_list = feeds.get("resources", [])
    results["feeds"] = []
    print(f"  Total feeds: {len(feed_list)}")
    for feed in feed_list:
        info = {
            "id": feed.get("id"),
            "name": feed.get("name"),
            "format": feed.get("format", {}).get("fileEncoding"),
            "contentType": feed.get("contentType"),
            "fetchSchedule": feed.get("fetchSchedule", {}).get("weekday") or feed.get("fetchSchedule", {}).get("hour"),
            "fileName": feed.get("fileName"),
            "targets": feed.get("targets", []),
        }
        results["feeds"].append(info)
        targets = feed.get("targets", [])
        countries = [t.get("country") for t in targets]
        lang = [t.get("language") for t in targets]
        print(f"  [{feed.get('id')}] {feed.get('name')}")
        print(f"    Type: {feed.get('contentType')} | Countries: {countries} | Lang: {lang}")
        print(f"    File: {feed.get('fileName')} | Fetch: {feed.get('fetchSchedule',{})}")
except Exception as e:
    results["feeds"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── Save full report ──────────────────────────────────────────────────────────
os.makedirs("outputs", exist_ok=True)
with open("outputs/gmc_full_audit.json", "w") as f:
    json.dump(results, f, indent=2)
print("\n\nFull audit saved to outputs/gmc_full_audit.json")
