#!/usr/bin/env python3
"""
ads_geo_audit.py — READ-ONLY. Compare Google Ads campaign location targets to Shopify Markets.

Lists every active/paused campaign's positive location targets, then flags countries that are
not in a Shopify Market. Campaigns with no location criteria target all countries (flagged too).
Writes outputs/ads_geo_audit.json. Makes no changes in Google Ads or Shopify.

Env: GOOGLE_ADS_DEVELOPER_TOKEN / _CLIENT_ID / _CLIENT_SECRET / _REFRESH_TOKEN,
     SHOPIFY_CLIENT_ID + SHOPIFY_CLIENT_SECRET (or SHOPIFY_ADMIN_TOKEN)
"""
import json
import os
import sys

import requests
from google.ads.googleads.client import GoogleAdsClient

CUSTOMER_ID = "1137623123"
SHOP = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION = "2026-04"

MARKETS_QUERY = """
query { markets(first: 50) { nodes { name status
  conditions { regionsCondition { regions(first: 250) { nodes { ... on MarketRegionCountry { code } } } } } } } }
"""


def shopify_token() -> str:
    cid, secret = os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET")
    if cid and secret:
        r = requests.post(f"https://{SHOP}/admin/oauth/access_token", timeout=30,
                          json={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
        if r.status_code == 200:
            return r.json()["access_token"]
    token = os.environ.get("SHOPIFY_ADMIN_TOKEN")
    if not token:
        sys.exit("ERROR: no Shopify credentials available.")
    return token


def market_countries() -> set:
    r = requests.post(f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json", timeout=60,
                      headers={"X-Shopify-Access-Token": shopify_token()}, json={"query": MARKETS_QUERY})
    r.raise_for_status()
    codes = set()
    for m in r.json()["data"]["markets"]["nodes"]:
        if m["status"] != "ACTIVE":
            continue
        regions = ((m.get("conditions") or {}).get("regionsCondition") or {}).get("regions", {}).get("nodes", [])
        codes.update(x["code"] for x in regions if x.get("code"))
    return codes


def ads_client() -> GoogleAdsClient:
    return GoogleAdsClient.load_from_dict({
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": CUSTOMER_ID,
        "use_proto_plus": True,
    })


def campaign_locations(ga) -> tuple:
    """(campaigns {id: {name, status}}, positives {id: [geo]}, negatives {id: [geo]}, proximity {campaign ids})"""
    campaigns, pos, neg = {}, {}, {}
    for row in ga.search(customer_id=CUSTOMER_ID, query="""
            SELECT campaign.id, campaign.name, campaign.status FROM campaign
            WHERE campaign.status != 'REMOVED'"""):
        campaigns[row.campaign.id] = {"name": row.campaign.name, "status": row.campaign.status.name}
    for row in ga.search(customer_id=CUSTOMER_ID, query="""
            SELECT campaign.id, campaign_criterion.negative, campaign_criterion.location.geo_target_constant
            FROM campaign_criterion
            WHERE campaign_criterion.type = 'LOCATION' AND campaign.status != 'REMOVED'
              AND campaign_criterion.status != 'REMOVED'"""):
        geo = row.campaign_criterion.location.geo_target_constant
        if geo:
            (neg if row.campaign_criterion.negative else pos).setdefault(row.campaign.id, []).append(geo)
    proximity = {row.campaign.id for row in ga.search(customer_id=CUSTOMER_ID, query="""
            SELECT campaign.id FROM campaign_criterion
            WHERE campaign_criterion.type = 'PROXIMITY' AND campaign.status != 'REMOVED'
              AND campaign_criterion.status != 'REMOVED'""")}
    return campaigns, pos, neg, proximity


def resolve_geo(ga, resources: set) -> dict:
    """geo resource name -> {name, country_code, target_type}"""
    out, items = {}, sorted(resources)
    for i in range(0, len(items), 100):
        names = ", ".join(f"'{x}'" for x in items[i:i + 100])
        for row in ga.search(customer_id=CUSTOMER_ID, query=f"""
                SELECT geo_target_constant.resource_name, geo_target_constant.name,
                       geo_target_constant.country_code, geo_target_constant.target_type
                FROM geo_target_constant WHERE geo_target_constant.resource_name IN ({names})"""):
            g = row.geo_target_constant
            out[g.resource_name] = {"name": g.name, "country": g.country_code, "type": g.target_type}
    return out


def main():
    markets = market_countries()
    print(f"Shopify Markets countries (active): {len(markets)}")
    ga = ads_client().get_service("GoogleAdsService")
    campaigns, pos, neg, proximity = campaign_locations(ga)
    geo = resolve_geo(ga, {g for lst in list(pos.values()) + list(neg.values()) for g in lst})
    report = {"markets_countries": sorted(markets), "campaigns": []}
    for cid, c in campaigns.items():
        targeted = sorted({geo.get(g, {}).get("country", g) for g in pos.get(cid, [])})
        excluded = sorted({geo.get(g, {}).get("country", g) for g in neg.get(cid, [])})
        outside = sorted(set(targeted) - markets)
        has_radius = cid in proximity
        entry = {"id": cid, **c, "targets_all_countries": not targeted and not has_radius,
                 "has_proximity_targets": has_radius, "targeted": targeted,
                 "excluded": excluded, "outside_markets": outside,
                 "in_markets_not_targeted": sorted(markets - set(targeted)) if targeted else []}
        report["campaigns"].append(entry)
        print(f"\n[{c['status']}] {c['name']} (id={cid})")
        if has_radius:
            print("  Has PROXIMITY (radius) targets: NOT compared against Markets, review manually")
        elif not targeted:
            print("  No location criteria -> targets ALL countries (includes non-market countries)")
        print(f"  Targeted ({len(targeted)}): {targeted}")
        print(f"  Outside Shopify Markets ({len(outside)}): {outside}")
        if excluded:
            print(f"  Excluded: {excluded}")
    os.makedirs("outputs", exist_ok=True)
    with open("outputs/ads_geo_audit.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print("\nSaved outputs/ads_geo_audit.json")


if __name__ == "__main__":
    main()
