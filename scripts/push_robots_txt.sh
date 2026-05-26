#!/bin/bash
set -e

echo "=== Step 1: Verify token ==="
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  "https://lngndny.myshopify.com/admin/api/2026-04/shop.json")
echo "Token check: HTTP $STATUS"
[ "$STATUS" != "200" ] && echo "Token invalid ($STATUS)" && exit 1

echo "=== Step 2: Get active theme ID ==="
THEME_RESPONSE=$(curl -s \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  "https://lngndny.myshopify.com/admin/api/2026-04/themes.json")
THEME_ID=$(echo "$THEME_RESPONSE" | python3 -c "
import json,sys
themes = json.load(sys.stdin)['themes']
active = next((t for t in themes if t['role']=='main'), None)
if active:
    print(active['id'])
    import sys; print(f\"Theme: {active['name']}\", file=sys.stderr)
")
echo "Active theme ID: $THEME_ID"

echo "=== Step 3: Push robots.txt.liquid ==="
ASSET_VALUE=$(cat scripts/robots_v2.liquid)
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  -X PUT \
  -H "X-Shopify-Access-Token: $SHOPIFY_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  "https://lngndny.myshopify.com/admin/api/2026-04/themes/$THEME_ID/assets.json" \
  --data-binary "{\"asset\":{\"key\":\"templates/robots.txt.liquid\",\"value\":$(echo "$ASSET_VALUE" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}")

HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | grep -v "HTTP_STATUS:")

echo "HTTP Status: $HTTP_STATUS"
if [[ "$HTTP_STATUS" == "200" || "$HTTP_STATUS" == "201" ]]; then
  echo "SUCCESS: robots.txt.liquid pushed to live Shopify theme"
  echo "$BODY" | python3 -c "import json,sys; a=json.load(sys.stdin).get('asset',{}); print(f\"  Key: {a.get('key')} | Updated: {a.get('updated_at')}\")"
else
  echo "ERROR: $BODY"
  exit 1
fi