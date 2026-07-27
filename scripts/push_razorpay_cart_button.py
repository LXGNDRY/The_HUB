"""
push_razorpay_cart_button.py — Push lb-razorpay.js to the live Shopify theme.

Reads env vars:
  SHOPIFY_ADMIN_TOKEN    — shpat_...
  RAZORPAY_BACKEND_URL   — https://lb-razorpay-backend-xxx-uc.a.run.app
  RAZORPAY_KEY_ID        — rzp_live_... (public key ID only)

Usage:
  python scripts/push_razorpay_cart_button.py [--dry-run]
"""

import os
import sys
import time
import threading
import argparse
import requests

DOMAIN   = "lngndny.myshopify.com"
API_VER  = "2026-04"
BASE_URL = f"https://{DOMAIN}/admin/api/{API_VER}"

CLIENT_ID     = os.environ.get("SHOPIFY_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SHOPIFY_CLIENT_SECRET", "")
_TOKEN_REFRESH_BUFFER = 300

class _TokenCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0

    def get(self):
        with self._lock:
            if time.time() >= (self._expires_at - _TOKEN_REFRESH_BUFFER):
                self._refresh()
            return self._token

    def _refresh(self):
        if not CLIENT_ID or not CLIENT_SECRET:
            raise RuntimeError("SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET must be set")
        r = requests.post(
            f"https://{DOMAIN}/admin/oauth/access_token",
            json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "grant_type": "client_credentials"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 86399))

_token_cache = _TokenCache()

def _headers():
    return {"X-Shopify-Access-Token": _token_cache.get(), "Content-Type": "application/json"}

JS_SOURCE_PATH = os.path.join(os.path.dirname(__file__), "razorpay_cart_button.js")


def push_razorpay_button(razorpay_backend_url: str, razorpay_key_id: str, dry_run: bool = False) -> dict:
    if not razorpay_backend_url:
        raise ValueError("RAZORPAY_BACKEND_URL is not set")
    if not razorpay_key_id:
        raise ValueError("RAZORPAY_KEY_ID is not set")

    # 1. Find live theme
    print("Step 1: Finding active theme...")
    resp = requests.get(f"{BASE_URL}/themes.json", headers=_headers(), timeout=15)
    resp.raise_for_status()
    themes = resp.json()["themes"]
    active = next((t for t in themes if t["role"] == "main"), None)
    if not active:
        raise RuntimeError("No active (main) theme found")
    theme_id = active["id"]
    print(f"  Active theme: {active['name']} (id={theme_id})")

    # 2. Read JS asset from LegendaryBrandingTheme worktree if available,
    #    otherwise fall back to scripts/razorpay_cart_button.js
    worktree_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "legendarybrandingtheme", "assets", "lb-razorpay.js"
    )
    if os.path.exists(worktree_path):
        js_path = os.path.realpath(worktree_path)
    elif os.path.exists(JS_SOURCE_PATH):
        js_path = JS_SOURCE_PATH
    else:
        raise FileNotFoundError(
            "Cannot find lb-razorpay.js. Expected at ../legendarybrandingtheme/assets/lb-razorpay.js "
            "or scripts/razorpay_cart_button.js"
        )

    print(f"Step 2: Reading JS from {js_path} ...")
    js_content = open(js_path).read()
    print(f"  {len(js_content)} chars")

    # 3. Push asset
    asset_key = "assets/lb-razorpay.js"
    print(f"Step 3: Pushing {asset_key} to theme {theme_id} ...")
    if dry_run:
        print(f"  DRY RUN — would PUT assets/{asset_key} ({len(js_content)} chars)")
    else:
        put_url = f"{BASE_URL}/themes/{theme_id}/assets.json"
        r = requests.put(
            put_url,
            headers=_headers(),
            json={"asset": {"key": asset_key, "value": js_content}},
            timeout=30
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Asset PUT failed ({r.status_code}): {r.text[:500]}")
        asset = r.json().get("asset", {})
        print(f"  Pushed: {asset.get('key')} at {asset.get('updated_at')}")

    # 4. Fetch cart-summary.liquid, inject real values, push back
    snippet_key = "snippets/cart-summary.liquid"
    print(f"Step 4: Patching {snippet_key} with real backend URL + key ID ...")
    get_url = f"{BASE_URL}/themes/{theme_id}/assets.json"
    gr = requests.get(get_url, headers=_headers(), params={"asset[key]": snippet_key}, timeout=15)
    gr.raise_for_status()
    snippet_content = gr.json()["asset"]["value"]

    patched = snippet_content.replace("'GCP_BASE_URL'", f"'{razorpay_backend_url}'")
    patched = patched.replace("'RZP_KEY_ID'", f"'{razorpay_key_id}'")

    if patched == snippet_content:
        print("  No placeholders found — snippet may already be patched or placeholders missing.")
    elif dry_run:
        print(f"  DRY RUN — would PUT {snippet_key} with injected values")
    else:
        pr = requests.put(
            get_url,
            headers=_headers(),
            json={"asset": {"key": snippet_key, "value": patched}},
            timeout=30
        )
        if pr.status_code not in (200, 201):
            raise RuntimeError(f"Snippet PUT failed ({pr.status_code}): {pr.text[:500]}")
        s_asset = pr.json().get("asset", {})
        print(f"  Patched: {s_asset.get('key')} at {s_asset.get('updated_at')}")

    result = {
        "status": "dry_run" if dry_run else "pushed",
        "theme_id": theme_id,
        "theme_name": active["name"],
        "js_key": asset_key,
        "snippet_key": snippet_key,
    }
    print(f"\nDone. {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    push_razorpay_button(
        razorpay_backend_url=os.environ.get("RAZORPAY_BACKEND_URL", ""),
        razorpay_key_id=os.environ.get("RAZORPAY_KEY_ID", ""),
        dry_run=args.dry_run,
    )
