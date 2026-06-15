"""
gmc_attribute_rules_audit.py
Pull all feed rules, supplemental feeds, and attribute mappings from GMC
Focus: color and age_group gaps
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

# ── 1. Datafeeds (primary + supplemental) ────────────────────────────────────
print("\n=== 1. DATAFEEDS ===")
try:
    feeds = svc.datafeeds().list(merchantId=M).execute()
    feed_list = feeds.get("resources", [])
    print(f"  Total feeds: {len(feed_list)}")
    results["feeds"] = []
    for feed in feed_list:
        info = {
            "id": feed.get("id"),
            "name": feed.get("name"),
            "contentType": feed.get("contentType"),
            "targets": feed.get("targets", []),
            "fileName": feed.get("fileName"),
        }
        results["feeds"].append(info)
        print(f"  [{feed.get('id')}] {feed.get('name')} | type={feed.get('contentType')}")
        print(f"    Targets: {feed.get('targets', [])}")
except Exception as e:
    results["feeds"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 2. Datafeed statuses (to see processing errors) ───────────────────────────
print("\n=== 2. DATAFEED STATUSES ===")
try:
    statuses = svc.datafeedstatuses().list(merchantId=M).execute()
    status_list = statuses.get("resources", [])
    print(f"  Total feed statuses: {len(status_list)}")
    results["feed_statuses"] = []
    for s in status_list:
        info = {
            "feedId": s.get("datafeedId"),
            "country": s.get("country"),
            "language": s.get("language"),
            "itemsTotal": s.get("itemsTotal"),
            "itemsValid": s.get("itemsValid"),
            "errors": s.get("errors", [])[:3],
            "warnings": s.get("warnings", [])[:3],
        }
        results["feed_statuses"].append(info)
        print(f"  Feed {s.get('datafeedId')} [{s.get('country')}/{s.get('language')}]: {s.get('itemsValid')}/{s.get('itemsTotal')} valid")
        for err in s.get("errors", [])[:3]:
            print(f"    ERROR: {err.get('message')} (count={err.get('count')})")
        for warn in s.get("warnings", [])[:3]:
            print(f"    WARN:  {warn.get('message')} (count={warn.get('count')})")
except Exception as e:
    results["feed_statuses"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 3. Product statuses — find products missing color or age_group ─────────────
print("\n=== 3. PRODUCTS MISSING COLOR / AGE_GROUP ===")
try:
    missing_color = []
    missing_age_group = []
    missing_both = []
    
    req = svc.productstatuses().list(merchantId=M, maxResults=250)
    page = 0
    while req and page < 40:  # cap at 10K products
        resp = req.execute(num_retries=3)
        for item in resp.get("resources", []):
            issues = item.get("itemLevelIssues", [])
            issue_codes = [i.get("code","") for i in issues if i.get("destination") == "Shopping"]
            
            has_color_issue = any("color" in c.lower() for c in issue_codes)
            has_age_issue = any("age" in c.lower() for c in issue_codes)
            
            if has_color_issue and has_age_issue:
                missing_both.append({"id": item.get("productId"), "title": item.get("title")})
            elif has_color_issue:
                missing_color.append({"id": item.get("productId"), "title": item.get("title")})
            elif has_age_issue:
                missing_age_group.append({"id": item.get("productId"), "title": item.get("title")})
        
        req = svc.productstatuses().list_next(req, resp)
        page += 1
    
    results["missing_attributes"] = {
        "missing_color_only": len(missing_color),
        "missing_age_only": len(missing_age_group),
        "missing_both": len(missing_both),
        "color_sample": missing_color[:10],
        "age_sample": missing_age_group[:10],
        "both_sample": missing_both[:10],
    }
    print(f"  Missing color only:     {len(missing_color)}")
    print(f"  Missing age_group only: {len(missing_age_group)}")
    print(f"  Missing both:           {len(missing_both)}")
    
    if missing_color[:5]:
        print(f"\n  COLOR SAMPLE:")
        for p in missing_color[:5]:
            print(f"    {p['title']}")
    if missing_age_group[:5]:
        print(f"\n  AGE_GROUP SAMPLE:")
        for p in missing_age_group[:5]:
            print(f"    {p['title']}")
    if missing_both[:5]:
        print(f"\n  MISSING BOTH SAMPLE:")
        for p in missing_both[:5]:
            print(f"    {p['title']}")

except Exception as e:
    results["missing_attributes"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── 4. Sample actual product data to see what fields are populated ─────────────
print("\n=== 4. SAMPLE PRODUCT ATTRIBUTE CHECK ===")
try:
    products = svc.products().list(merchantId=M, maxResults=20).execute()
    sample_issues = []
    for p in products.get("resources", []):
        color = p.get("color", "")
        age_group = p.get("ageGroup", "")
        gender = p.get("gender", "")
        condition = p.get("condition", "")
        if not color or not age_group:
            sample_issues.append({
                "id": p.get("id"),
                "title": p.get("title","")[:60],
                "color": color or "MISSING",
                "ageGroup": age_group or "MISSING",
                "gender": gender or "MISSING",
                "condition": condition or "MISSING",
            })
    
    results["attribute_sample"] = sample_issues[:15]
    print(f"  Products with missing attributes (sample of 20):")
    for p in sample_issues[:10]:
        print(f"  [{p['id'][-20:]}] {p['title']}")
        print(f"    color={p['color']} | ageGroup={p['ageGroup']} | gender={p['gender']}")

except Exception as e:
    results["attribute_sample"] = {"error": str(e)}
    print(f"  ERROR: {e}")

# ── Save ───────────────────────────────────────────────────────────────────────
os.makedirs("outputs", exist_ok=True)
with open("outputs/gmc_attribute_rules_audit.json", "w") as f:
    json.dump(results, f, indent=2)
print("\n\nSaved to outputs/gmc_attribute_rules_audit.json")
