import requests, os
ADMIN_TOKEN = os.environ.get("SHOPIFY_ADMIN_TOKEN", "")
CLIENT_ID = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
SHOP = "lngndny.myshopify.com"
if ADMIN_TOKEN:
    token = ADMIN_TOKEN
else:
    token_resp = requests.post(f"https://{SHOP}/admin/oauth/access_token",
        data={"grant_type":"client_credentials","client_id":CLIENT_ID,"client_secret":CLIENT_SECRET})
    token = token_resp.json()["access_token"]
headers = {"X-Shopify-Access-Token": token}
r = requests.get(f"https://{SHOP}/admin/api/2026-04/shipping_zones.json", headers=headers)
zones = r.json().get("shipping_zones", [])
print(f"Total zones: {len(zones)}")
for z in zones:
    countries = [c.get("name") for c in z.get("countries", [])]
    print(f"\nZONE: {z['name']} ({len(countries)} countries)")
    print(f"  Countries: {', '.join(countries[:20])}{'...' if len(countries)>20 else ''}")
    for rate in z.get("price_based_shipping_rates", []):
        mn = rate.get('min_order_subtotal') or '0'
        mx = rate.get('max_order_subtotal') or 'any'
        print(f"  Price rate: {rate['name']} — ${rate['price']} | order ${mn}–${mx}")
    for rate in z.get("weight_based_shipping_rates", []):
        print(f"  Weight rate: {rate['name']} — ${rate['price']}")
    for rate in z.get("carrier_shipping_rate_providers", []):
        print(f"  Carrier: {rate.get('carrier_service',{}).get('name','?')}")
