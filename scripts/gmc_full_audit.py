"""
gmc_full_audit.py — Full GMC account audit (Merchant API v1, read-only)
Covers: account info, account issues, product statuses, shipping, ads link, data sources
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules import merchant_api as gmc  # noqa: E402

AD_TARGETS = {
    'US', 'GB', 'CA', 'FR', 'DE', 'IE', 'ES', 'IT', 'AU', 'NZ', 'JP', 'KR', 'SG', 'HK', 'NL', 'BE', 'CH', 'NO',
    'SE', 'DK', 'FI', 'AT', 'PT', 'GR', 'CZ', 'PL', 'HU', 'RO', 'AE', 'QA', 'KW', 'BH', 'SA', 'IL', 'MX', 'AR',
    'CL', 'CO', 'EC', 'PE', 'DO', 'SV', 'GT', 'JM', 'PA', 'PR', 'TT', 'KZ', 'AM', 'GE', 'MA', 'EG', 'JO', 'LB',
    'ZA', 'MY',
}

results = {}


def run(title, key, fn):
    print(f"\n=== {title} ===")
    try:
        results[key] = fn()
    except Exception as e:  # keep going so one failing endpoint doesn't hide the rest
        results[key] = {"error": str(e)}
        print(f"  ERROR: {e}")


def account_info():
    a = gmc.account()
    print(f"  Name:    {a.get('accountName')}")
    print(f"  Website: {a.get('homepageUri') or a.get('homepage')}")
    print(f"  Time zone: {a.get('timeZone', {}).get('id')} | Language: {a.get('languageCode')}")
    return a


def account_issues():
    issues = gmc.account_issues()
    print(f"  Account-level issues: {len(issues)}")
    for i in issues:
        print(f"    [{i.get('severity', '?')}] {i.get('title')}")
    return issues


def product_statuses():
    total = 0
    disapproved = {}
    warnings = {}
    for p in gmc.products():
        total += 1
        status = p.get("productStatus", {})
        for d in status.get("destinationStatuses", []):
            if d.get("disapprovedCountries"):
                disapproved[p.get("offerId")] = d.get("reportingContext")
        for i in status.get("itemLevelIssues", []):
            key = f"{i.get('severity')}: {i.get('description') or i.get('code')}"
            warnings[key] = warnings.get(key, 0) + 1
    print(f"  Total: {total} | With disapproved countries: {len(disapproved)}")
    for k, v in sorted(warnings.items(), key=lambda kv: -kv[1])[:15]:
        print(f"    {v:>5}  {k}")
    return {"total": total, "disapproved_offers": len(disapproved), "issue_counts": warnings}


def shipping():
    s = gmc.shipping_settings()
    services = s.get("services", [])
    covered, free = set(), set()
    for svc in services:
        groups = svc.get("rateGroups", [])
        rate = gmc.flat_rate(groups[0]) if groups else None
        for c in svc.get("deliveryCountries", []):
            covered.add(c)
            if rate == "0.00":
                free.add(c)
    missing = sorted(AD_TARGETS - covered)
    print(f"  Services: {len(services)} | Countries covered: {len(covered)} | Free shipping: {len(free)}")
    print(f"  Ad targets missing shipping: {missing or 'None'}")
    return {"services": len(services), "countries": sorted(covered), "free": sorted(free),
            "ad_targets_missing_shipping": missing}


def ads_link():
    links = [s for s in gmc.account_services() if s.get("provider") == "providers/GOOGLE_ADS"]
    for s in links:
        state = s.get("handshake", {}).get("approvalState")
        print(f"  AdsID: {s.get('externalAccountId')} | approval: {state} "
              f"| campaignsManagement: {s.get('campaignsManagement')}")
    if not links:
        print("  No Ads links found")
    return links


def feeds():
    rows = gmc.data_sources()
    print(f"  Total data sources: {len(rows)}")
    for ds in rows:
        kind = "primary" if ds.get("primaryProductDataSource") else (
            "supplemental" if ds.get("supplementalProductDataSource") else "other")
        print(f"  [{ds.get('dataSourceId')}] {ds.get('displayName')} | {kind} | input={ds.get('input')}")
    return rows


run("1. ACCOUNT INFO", "account", account_info)
run("2. ACCOUNT ISSUES", "account_issues", account_issues)
run("3. PRODUCT STATUSES", "products", product_statuses)
run("4. SHIPPING", "shipping", shipping)
run("5. GOOGLE ADS LINK", "ads_links", ads_link)
run("6. DATA SOURCES / FEEDS", "feeds", feeds)

os.makedirs("outputs", exist_ok=True)
with open("outputs/gmc_full_audit.json", "w") as f:
    json.dump(results, f, indent=2, default=str)
print("\nFull audit saved to outputs/gmc_full_audit.json")
