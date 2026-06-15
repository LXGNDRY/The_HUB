import json, os, sys
from google.oauth2 import service_account
from googleapiclient.discovery import build

SA_KEY_JSON = os.environ.get("GCP_SA_KEY")
sa_info = json.loads(SA_KEY_JSON)
creds = service_account.Credentials.from_service_account_info(
    sa_info, scopes=["https://www.googleapis.com/auth/content"])
svc = build("content", "v2.1", credentials=creds)
M = 582171114

# All 56 ad-targeted countries
AD_TARGETS = {
    'US','GB','CA','FR','DE','IE','ES','IT','AU','NZ','JP','KR','SG','HK',
    'NL','BE','CH','NO','SE','DK','FI','AT','PT','GR','CZ','PL','HU','RO',
    'AE','QA','KW','BH','SA','IL','MX','AR','CL','CO','EC','PE','DO','SV',
    'GT','JM','PA','PR','TT','KZ','AM','GE','MA','EG','JO','LB','ZA','MY'
}

# Check shipping coverage
shipping = svc.shippingsettings().get(merchantId=M, accountId=M).execute()
svcs = shipping.get("services", [])
covered = {s.get("deliveryCountry") for s in svcs}
missing = AD_TARGETS - covered

print(f"Shipping services: {len(svcs)}")
print(f"Countries covered: {len(covered)}")
print(f"Ad targets missing shipping: {sorted(missing) or 'None ✓'}")

# Check product status per country for the missing ones
if missing:
    print(f"\nChecking product availability for missing countries...")
    # Sample first 10 products to see if they have records for missing countries
    prods = svc.products().list(merchantId=M, maxResults=10).execute()
    missing_country_products = {c: 0 for c in missing}
    for p in prods.get("resources", []):
        tc = p.get("targetCountry","")
        if tc in missing_country_products:
            missing_country_products[tc] += 1
    print(f"Product sample check: {missing_country_products}")
