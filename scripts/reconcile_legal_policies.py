#!/usr/bin/env python3
"""Safely reconcile Shopify legal policies with the active shipping profile.

Requires SHOPIFY_ADMIN_TOKEN with read_legal_policies, write_legal_policies,
and access to delivery profiles; supports DRY_RUN=1 and pre-write backups.
Does not change shipping rates, tax settings or duties collection settings.
"""
import datetime
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

SHOP = os.environ.get("SHOPIFY_SHOP_DOMAIN", "lngndny.myshopify.com")
API = "2026-10"
TOKEN = os.environ["SHOPIFY_ADMIN_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
BACKUP_DIR = pathlib.Path("policy-backups")
GQL_URL = f"https://{SHOP}/admin/api/{API}/graphql.json"

def graphql(query, variables=None):
    data = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(GQL_URL, data=data, headers={
        "X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Shopify HTTP {exc.code}; check token and scopes") from exc
    if result.get("errors"):
        raise RuntimeError(f"Shopify GraphQL error: {result['errors']}")
    return result["data"]

QUERY = """query {
 shop { shopPolicies { type body updatedAt } }
 deliveryProfiles(first:10) { nodes { default name profileLocationGroups {
   locationGroupZones(first:50) { nodes { zone { name }
     methodDefinitions(first:30) { nodes { name active
       rateProvider { __typename ... on DeliveryRateDefinition { price { amount currencyCode } } }
       methodConditions { field operator conditionCriteria {
         __typename ... on MoneyV2 { amount currencyCode }
       }}
     }}
   }}
 }}}
}"""
UPDATE = """mutation ($shopPolicy: ShopPolicyInput!) {
 shopPolicyUpdate(shopPolicy:$shopPolicy) {
   shopPolicy { type updatedAt body }
   userErrors { field message }
 }
}"""

def shipping_rates_verified(data):
    profiles = data["deliveryProfiles"]["nodes"]
    if len(profiles) != 1 or not profiles[0]["default"]:
        raise RuntimeError("Shipping profiles differ from the verified single General profile; refusing to change policies")
    groups = profiles[0]["profileLocationGroups"]
    zones = [z for g in groups for z in g["locationGroupZones"]["nodes"]]
    if len(zones) != 6:
        raise RuntimeError("Expected six shipping zones; refusing to update policy")
    for node in zones:
        methods = node["methodDefinitions"]["nodes"]
        signatures = set()
        for method in methods:
            if not method["active"] or method["rateProvider"]["__typename"] != "DeliveryRateDefinition":
                continue
            price = method["rateProvider"]["price"]
            conditions = tuple(sorted((c["field"], c["operator"], c["conditionCriteria"].get("amount"))
                                      for c in method["methodConditions"]))
            signatures.add((method["name"], price["amount"], price["currencyCode"], conditions))
        expected = {
            ("Standard", "5.0", "USD", (("TOTAL_PRICE", "GREATER_THAN_OR_EQUAL_TO", "0.0"), ("TOTAL_PRICE", "LESS_THAN_OR_EQUAL_TO", "99.99"))),
            ("Standard", "0.0", "USD", (("TOTAL_PRICE", "GREATER_THAN_OR_EQUAL_TO", "100.0"),)),
            ("Express", "12.0", "USD", ()),
        }
        if signatures != expected:
            raise RuntimeError("Rates/thresholds do not match expected configuration for " + node["zone"]["name"])
    print("Confirmed six zones: standard $5 below $100; free at $100+; express $12")

SHIPPING = """<article><h1>Shipping &amp; Delivery Policy</h1>
<p>Last updated: October 15, 2026</p>
<h2>Shipping Charges</h2>
<p>Standard shipping costs <strong>$5 USD</strong> on eligible merchandise orders below <strong>$100 USD</strong>. Standard shipping is <strong>free on eligible merchandise orders of $100 USD or more</strong>. Express shipping is <strong>$12 USD</strong> when available and selected. Final shipping choices and charges are presented at checkout; discounts may affect threshold eligibility.</p>
<h2>Order Processing and Print-on-Demand</h2>
<p>Orders are typically processed within <strong>2–3 business days</strong>, excluding weekends and public holidays. Many garments are manufactured or printed on demand by fulfillment partners. Production, quality checks and packing can affect dispatch; processing and shipping transit are separate.</p>
<h2>Destinations and Delivery Estimates</h2>
<p>We ship within the United States and internationally to <strong>supported destinations</strong>, not every country. Delivery eligibility is confirmed at checkout. Delivery estimates vary by destination, fulfillment partner, carrier and customs clearance and are not guarantees.</p>
<h2>Import Duties and Taxes</h2>
<p>Our intended international pricing approach is to cover applicable import duties for supported orders rather than charge customers separately at delivery. The specific treatment of duties may vary by destination and checkout configuration; we do not guarantee that duties are prepaid unless this is confirmed for your order. Applicable sales taxes and any import charges collected by checkout are displayed before payment. If a carrier or customs authority requests an unexpected import payment, contact us before paying so we can investigate. Customs may delay delivery.</p>
<h2>Tracking and Shipping Issues</h2>
<p>Tracking is sent when available after dispatch and may take time to activate. For missing, late, damaged or incorrectly delivered parcels, contact <a href="mailto:lb@legendary-branding.com">lb@legendary-branding.com</a> with your order number. We will investigate with the carrier or fulfillment partner and determine an appropriate resolution under applicable law and our refund policy.</p>
<p>The rates and delivery options displayed during checkout govern the shipping method selected for that purchase.</p></article>"""

SECTION7 = """<section id="section-7" style="margin-bottom:40px;">
<h2>7. Shipping &amp; Delivery</h2>
<p>Standard shipping costs $5 USD for eligible merchandise orders below $100 USD, and standard shipping is free for eligible merchandise orders of $100 USD or more. Express shipping costs $12 USD when available and selected. Delivery is limited to supported checkout destinations. Orders are normally processed within 2–3 business days, excluding weekends and holidays. Print-on-demand production and shipping transit time may be additional. Delivery estimates are not guarantees.</p>
<p>Our intended pricing approach is to cover applicable import duties for supported international orders, but duties are not represented as prepaid unless confirmed by the applicable checkout and shipping arrangements. Sales taxes and any separately collected import charges are displayed before payment. Please contact us regarding any unexpected carrier or customs payment request. See our <a href="/policies/shipping-policy">Shipping Policy</a> for details. Your statutory consumer rights remain unaffected.</p>
</section>"""

def main():
    data = graphql(QUERY)
    shipping_rates_verified(data)
    policies = {p["type"]: p for p in data["shop"]["shopPolicies"]}
    for required in ("SHIPPING_POLICY", "TERMS_OF_SERVICE"):
        if required not in policies:
            raise RuntimeError("Missing live policy " + required)
    terms = policies["TERMS_OF_SERVICE"]["body"]
    start, end = terms.find('<section id="section-7"'), terms.find('<section id="section-8"')
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("Unexpected Terms section structure; refusing blind replacement")
    updated_terms = terms[:start] + SECTION7 + terms[end:]
    updated_terms = updated_terms.replace("Last updated: August 2026", "Last updated: October 15, 2026")
    if "free worldwide shipping" in updated_terms.lower():
        raise RuntimeError("Stale 'free worldwide shipping' found outside Terms §7")
    proposed = {"SHIPPING_POLICY": SHIPPING, "TERMS_OF_SERVICE": updated_terms}
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"shopify-policies-before-{stamp}.json"
    backup.write_text(json.dumps({k: policies[k] for k in proposed}, indent=2), encoding="utf-8")
    print(f"Backup prepared: {backup}; dry_run={DRY_RUN}")
    if DRY_RUN:
        print("DRY_RUN: no writes performed")
        return
    # Check for concurrent edits before applying either update.
    fresh = {p["type"]: p for p in graphql(QUERY)["shop"]["shopPolicies"]}
    for typ in proposed:
        if fresh[typ]["body"] != policies[typ]["body"]:
            raise RuntimeError("Live policy changed during run: " + typ)
    for typ, body in proposed.items():
        result = graphql(UPDATE, {"shopPolicy": {"type": typ, "body": body}})["shopPolicyUpdate"]
        if not result or result["userErrors"]:
            raise RuntimeError("Policy update failed for " + typ + ": " + json.dumps(result))
        if result["shopPolicy"]["body"] != body:
            raise RuntimeError("Unexpected policy body after mutation: " + typ)
        print("Applied and confirmed: " + typ)
    verify = {p["type"]: p for p in graphql(QUERY)["shop"]["shopPolicies"]}
    for typ, body in proposed.items():
        if verify[typ]["body"] != body:
            raise RuntimeError("Read-back verification mismatch: " + typ)
    print("Both Shopify policies verified live.")

if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
