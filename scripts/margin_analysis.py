"""
Margin Analysis — pulls all Shopify products with variant price, compare-at price,
and cost-per-item (unitCost via inventoryItem), then calculates gross margin and
suggests price adjustments to reach 35–40% target.

Output:
  reports/margin_analysis_YYYY-MM-DD.csv   — full variant-level detail
  stdout                                   — summary + lowest-margin products

Usage:
  python scripts/margin_analysis.py

Env vars required:
  SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET   (OAuth client credentials)
  -- OR --
  SHOPIFY_ADMIN_TOKEN                        (bootstrap token)
"""

import os
import csv
import sys
import json
import requests
from datetime import date, datetime

SHOP = os.environ.get("SHOPIFY_STORE_DOMAIN", "lngndny.myshopify.com")
API_VERSION = "2026-04"
GQL_URL = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"

TARGET_LOW = 35.0
TARGET_HIGH = 40.0
TARGET_MID = (TARGET_LOW + TARGET_HIGH) / 2.0  # 37.5%

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "reports")


def _get_token() -> str:
    token = os.environ.get("SHOPIFY_ADMIN_TOKEN", "").strip()
    if token:
        return token
    client_id = os.environ["SHOPIFY_CLIENT_ID"]
    client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]
    r = requests.post(
        f"https://{SHOP}/admin/oauth/access_token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def gql(query: str, variables: dict, headers: dict) -> dict:
    r = requests.post(
        GQL_URL,
        headers=headers,
        json={"query": query, "variables": variables},
        timeout=60,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body


PRODUCTS_QUERY = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      productType
      vendor
      status
      onlineStoreUrl
      variants(first: 100) {
        nodes {
          id
          sku
          title
          price
          compareAtPrice
          inventoryItem {
            unitCost {
              amount
              currencyCode
            }
          }
        }
      }
    }
  }
}
"""


def fetch_all_products(headers: dict) -> list:
    products = []
    cursor = None
    while True:
        data = gql(PRODUCTS_QUERY, {"cursor": cursor}, headers)
        page = data["data"]["products"]
        products.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return products


def calc_margin(price: float, cost: float) -> float:
    if price <= 0:
        return 0.0
    return (price - cost) / price * 100.0


def suggested_price(cost: float, margin_pct: float) -> float:
    """Minimum price to achieve margin_pct given cost."""
    if margin_pct >= 100:
        return float("inf")
    return cost / (1.0 - margin_pct / 100.0)


def main():
    print("Fetching Shopify token…")
    token = _get_token()
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }

    print("Pulling all products (with cost data)…")
    products = fetch_all_products(headers)
    print(f"  {len(products)} products fetched.\n")

    rows = []
    for p in products:
        if p.get("status") != "ACTIVE":
            continue
        for v in p["variants"]["nodes"]:
            price = float(v.get("price") or 0)
            compare_at = float(v.get("compareAtPrice") or 0)
            unit_cost_node = (v.get("inventoryItem") or {}).get("unitCost")

            if unit_cost_node and unit_cost_node.get("amount") is not None:
                cost = float(unit_cost_node["amount"])
                cost_missing = False
            else:
                cost = None
                cost_missing = True

            if cost_missing or price == 0:
                margin = None
                sugg_35 = None
                sugg_40 = None
                delta_35 = None
                below_target = False
            else:
                margin = calc_margin(price, cost)
                sugg_35 = suggested_price(cost, TARGET_LOW)
                sugg_40 = suggested_price(cost, TARGET_HIGH)
                delta_35 = sugg_35 - price  # positive = need to raise price
                below_target = margin < TARGET_LOW

            rows.append({
                "product_title": p["title"],
                "product_type": p.get("productType", ""),
                "vendor": p.get("vendor", ""),
                "variant_title": v.get("title", ""),
                "sku": v.get("sku", ""),
                "current_price": f"{price:.2f}",
                "compare_at_price": f"{compare_at:.2f}" if compare_at else "",
                "cost": f"{cost:.2f}" if cost is not None else "COST_MISSING",
                "current_margin_pct": f"{margin:.1f}" if margin is not None else "N/A",
                "suggested_price_35pct": f"{sugg_35:.2f}" if sugg_35 is not None else "N/A",
                "suggested_price_40pct": f"{sugg_40:.2f}" if sugg_40 is not None else "N/A",
                "delta_to_35pct": f"{delta_35:+.2f}" if delta_35 is not None else "N/A",
                "below_target": "YES" if below_target else ("COST_MISSING" if cost_missing else ""),
            })

    # ── Write CSV ────────────────────────────────────────────────────────────
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = os.path.join(REPORTS_DIR, f"margin_analysis_{date.today()}.csv")
    fieldnames = [
        "product_title", "product_type", "vendor", "variant_title", "sku",
        "current_price", "compare_at_price", "cost",
        "current_margin_pct", "suggested_price_35pct", "suggested_price_40pct",
        "delta_to_35pct", "below_target",
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # ── Summary ──────────────────────────────────────────────────────────────
    costed = [r for r in rows if r["cost"] != "COST_MISSING"]
    missing_cost = [r for r in rows if r["cost"] == "COST_MISSING"]
    below = [r for r in costed if r["below_target"] == "YES"]
    at_or_above = [r for r in costed if r["below_target"] == ""]

    margins = [float(r["current_margin_pct"]) for r in costed]
    avg_margin = sum(margins) / len(margins) if margins else 0

    print("=" * 65)
    print("MARGIN ANALYSIS SUMMARY")
    print(f"  Run date:          {date.today()}")
    print(f"  Active products:   {len(products)}")
    print(f"  Total variants:    {len(rows)}")
    print(f"  Variants w/ cost:  {len(costed)}")
    print(f"  Missing cost data: {len(missing_cost)}")
    print(f"  Average margin:    {avg_margin:.1f}%")
    print(f"  Below {TARGET_LOW}%:       {len(below)} variants")
    print(f"  At/above {TARGET_LOW}%:    {len(at_or_above)} variants")
    print("=" * 65)

    if below:
        print(f"\nLOWEST MARGIN VARIANTS (below {TARGET_LOW}%) — top 20:")
        sorted_below = sorted(below, key=lambda r: float(r["current_margin_pct"]))
        print(f"  {'Product':<40} {'SKU':<15} {'Price':>7} {'Cost':>7} {'Margin':>7} {'Need +$':>8}")
        print("  " + "-" * 90)
        for r in sorted_below[:20]:
            title = r["product_title"][:38]
            sku = (r["sku"] or "—")[:13]
            print(
                f"  {title:<40} {sku:<15} "
                f"${float(r['current_price']):>6.2f} "
                f"${float(r['cost']):>6.2f} "
                f"{float(r['current_margin_pct']):>6.1f}% "
                f"{r['delta_to_35pct']:>8}"
            )

    if missing_cost:
        print(f"\nVARIANTS MISSING COST DATA ({len(missing_cost)}) — enter cost in Shopify Admin → Products → variant:")
        for r in missing_cost[:15]:
            print(f"  - {r['product_title']} | {r['sku'] or 'no SKU'}")
        if len(missing_cost) > 15:
            print(f"  … and {len(missing_cost) - 15} more (see CSV)")

    print(f"\nFull report saved to: {filename}")
    return filename


if __name__ == "__main__":
    main()
