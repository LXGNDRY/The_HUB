"""
title_rotation_module.py — Title Rotation Engine for gmc_supplemental_feed.py
──────────────────────────────────────────────────────────────────────────────

DESIGN
──────
Each product category has a pool of keyword prefix variants. On every daily
cron run the engine:

  1. Fetches free-listing performance for the last 14 days via GMC reports.search
     (impressions, clicks, CTR per offer_id → maps back to product handle)
  2. Loads rotation state from GCS (title_rotation_state.json)
  3. For each product:
       a. LOCKED  → CTR >= LOCK_CTR_THRESHOLD for >= LOCK_MIN_DAYS consecutive
                    days: keep current prefix, do not rotate
       b. COOLING → rotated < COOLDOWN_DAYS ago: skip (let new title accumulate data)
       c. ROTATE  → everything else: advance to next prefix in pool
  4. Writes the chosen prefix into the record builder (replaces the static PREFIX_MAP lookup)
  5. Saves updated state back to GCS for the next run

STATE FILE (GCS: idx-lngndny / lb-feed-state / title_rotation_state.json)
──────────────────────────────────────────────────────────────────────────────
{
  "last_run": "2026-06-03",
  "products": {
    "<product_handle>": {
      "current_prefix_idx": 1,          // index into ROTATION_POOLS[category]
      "last_rotated": "2026-06-01",      // ISO date of last rotation
      "locked": false,                   // true = high performer, skip rotation
      "locked_since": null,              // ISO date lock was applied
      "lock_streak": 0,                  // consecutive days above CTR threshold
      "history": [                       // last 30 rotation events (for audit)
        {"date": "2026-06-01", "prefix_idx": 0, "ctr_at_rotation": 0.012}
      ]
    }
  }
}

LOCK THRESHOLDS (tunable)
──────────────────────────
LOCK_CTR_THRESHOLD = 0.04   # 4% CTR on free listings → high performer, lock it
LOCK_MIN_DAYS      = 7      # must sustain threshold for 7 days before locking
COOLDOWN_DAYS      = 7      # minimum days a new title must run before next rotation
UNLOCK_CTR         = 0.02   # if locked title drops below 2% CTR, unlock and rotate

ROTATION POOLS — 5 prefix variants per category
──────────────────────────────────────────────────
Each pool is ordered from broadest reach → most specific/niche.
The engine cycles through them in order (index % len(pool)).
Cadence: up to 1 rotation per product per COOLDOWN_DAYS days.
"""

import json, os, re
from datetime import date, datetime, timedelta
from google.oauth2 import service_account
from google.auth.transport.requests import Request as GoogleRequest
import requests as http_requests

# ── Thresholds ────────────────────────────────────────────────────────────────
LOCK_CTR_THRESHOLD = 0.04    # 4% free listing CTR → lock
LOCK_MIN_DAYS      = 7       # days above threshold before locking
COOLDOWN_DAYS      = 7       # min days between rotations
UNLOCK_CTR         = 0.02    # CTR below this unlocks a locked title
PERF_LOOKBACK_DAYS = 14      # days of performance data to fetch

# ── GCS state file location ───────────────────────────────────────────────────
GCS_BUCKET    = "lb-feed-state"          # create once in idx-lngndny project
GCS_OBJECT    = "title_rotation_state.json"
MERCHANT_ID   = "582171114"

# ── Rotation pools — 5 variants per category ─────────────────────────────────
# Ordered: broad → specific. Engine cycles index 0→1→2→3→4→0...
# All variants are purely keyword-driven (no brand name in prefix).
ROTATION_POOLS = {
    "hoodie": [
        "Heavyweight Oversized Streetwear Hoodie",           # current default
        "460GSM Oversized Pullover Hoodie Streetwear",
        "Premium Heavyweight Boxy Hoodie Men",
        "Streetwear Drop Shoulder Oversized Hoodie",
        "Luxury Heavyweight Fleece Hoodie Unisex",
    ],
    "crewneck": [
        "Heavyweight Oversized Crewneck Sweatshirt",          # current default
        "460GSM Boxy Crewneck Sweatshirt Streetwear",
        "Premium Oversized Fleece Crewneck Men",
        "Streetwear Drop Shoulder Crewneck Unisex",
        "Luxury Heavyweight Crewneck Sweatshirt",
    ],
    "sweatshirt": [
        "Heavyweight Streetwear Sweatshirt",                  # current default
        "Premium Oversized Fleece Sweatshirt Men",
        "Boxy Fit Heavyweight Sweatshirt Streetwear",
        "Drop Shoulder Sweatshirt Premium",
        "Streetwear Fleece Sweatshirt Unisex",
    ],
    "sweatpants": [
        "Premium Heavyweight Streetwear Sweatpants",          # current default
        "Oversized Wide Leg Sweatpants Men",
        "Baggy Fit Premium Sweatpants Streetwear",
        "Heavyweight Fleece Jogger Pants Unisex",
        "Streetwear Relaxed Fit Sweatpants Men",
    ],
    "jeans": [
        "Baggy Streetwear Denim Jeans Men",                   # current default
        "Wide Leg Baggy Denim Jeans Unisex",
        "Oversized Relaxed Fit Denim Jeans",
        "Premium Baggy Jean Streetwear Men",
        "Streetwear Wide Leg Denim Pants",
    ],
    "shorts": [
        "Premium Streetwear Athletic Shorts Unisex",          # current default
        "Oversized Streetwear Shorts Men",
        "Heavyweight Cotton Shorts Streetwear",
        "Boxy Fit Athletic Shorts Unisex",
        "Premium Mesh Streetwear Shorts Men",
    ],
    "polo": [
        "Premium Streetwear Polo Shirt Unisex",               # current default
        "Oversized Polo Shirt Streetwear Men",
        "Heavyweight Cotton Polo Shirt Unisex",
        "Boxy Fit Polo Shirt Premium Streetwear",
        "Streetwear Drop Shoulder Polo Men",
    ],
    "tank": [
        "Premium Streetwear Crop Tank Top Unisex",            # current default
        "Oversized Tank Top Streetwear Men",
        "Heavyweight Cotton Tank Top Unisex",
        "Boxy Fit Crop Tank Top Streetwear",
        "Streetwear Sleeveless Shirt Premium",
    ],
    "jacket": [
        "Premium Streetwear Jacket Unisex",                   # current default
        "Oversized Streetwear Outerwear Jacket Men",
        "Heavyweight Streetwear Bomber Jacket",
        "Boxy Fit Outerwear Jacket Streetwear",
        "Premium Water Resistant Jacket Men",
    ],
    "set": [
        "Streetwear Matching Hoodie Jogger Set",              # current default
        "Premium Matching Tracksuit Set Men",
        "Oversized Hoodie Sweatpants Set Streetwear",
        "Heavyweight Fleece Matching Set Unisex",
        "Premium Coord Set Streetwear Men",
    ],
    "tshirt": [
        "Heavyweight Graphic Streetwear T-Shirt",             # current default
        "280GSM Oversized Boxy T-Shirt Men",
        "Premium Heavyweight Drop Shoulder Tee",
        "Streetwear Graphic Tee Unisex Oversized",
        "Luxury Cotton Heavyweight T-Shirt Streetwear",
    ],
    "hat": [
        "Premium Streetwear Trucker Hat Unisex",              # current default
        "Adjustable Snapback Hat Streetwear",
        "City Logo Trucker Cap Premium",
        "Structured Snapback Streetwear Hat",
        "Premium Embroidered Cap Unisex",
    ],
}

# ── State I/O via GCS ─────────────────────────────────────────────────────────

def _gcs_headers(sa_key_json: str) -> dict:
    """Return auth headers for GCS JSON API using SA credentials."""
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_key_json),
        scopes=["https://www.googleapis.com/auth/devstorage.read_write"],
    )
    creds.refresh(GoogleRequest())
    return {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}


def load_state(sa_key_json: str) -> dict:
    """Load rotation state from GCS. Returns empty state if not found."""
    headers = _gcs_headers(sa_key_json)
    url = f"https://storage.googleapis.com/download/storage/v1/b/{GCS_BUCKET}/o/{GCS_OBJECT}?alt=media"
    r = http_requests.get(url, headers=headers, timeout=15)
    if r.status_code == 404:
        print("  [rotation] No state file found — starting fresh")
        return {"last_run": None, "products": {}}
    r.raise_for_status()
    return r.json()


def save_state(state: dict, sa_key_json: str) -> None:
    """Save rotation state to GCS."""
    headers = _gcs_headers(sa_key_json)
    # Ensure bucket exists (idempotent)
    bucket_url = f"https://storage.googleapis.com/storage/v1/b/{GCS_BUCKET}"
    br = http_requests.get(bucket_url, headers=headers, timeout=10)
    if br.status_code == 404:
        print(f"  [rotation] Creating GCS bucket {GCS_BUCKET}...")
        create_url = "https://storage.googleapis.com/storage/v1/b"
        http_requests.post(
            create_url,
            headers=headers,
            json={"name": GCS_BUCKET, "location": "US"},
            params={"project": os.environ.get("GCP_PROJECT_ID", "idx-lngndny")},
            timeout=15,
        ).raise_for_status()

    upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/{GCS_BUCKET}/o?uploadType=media&name={GCS_OBJECT}"
    upload_headers = {**headers, "Content-Type": "application/json"}
    http_requests.post(upload_url, headers=upload_headers, data=json.dumps(state, indent=2), timeout=15).raise_for_status()
    print(f"  [rotation] State saved to gs://{GCS_BUCKET}/{GCS_OBJECT}")


# ── GMC performance fetch ─────────────────────────────────────────────────────

def fetch_free_listing_performance(sa_key_json: str) -> dict:
    """
    Fetch 14-day free listing CTR per offer_id from GMC reports.search.
    Returns dict: { offer_id_str: {"impressions": int, "clicks": int, "ctr": float} }
    """
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_key_json),
        scopes=["https://www.googleapis.com/auth/content"],
    )
    creds.refresh(GoogleRequest())
    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}

    end_date   = date.today() - timedelta(days=1)   # yesterday (data lag)
    start_date = end_date - timedelta(days=PERF_LOOKBACK_DAYS - 1)

    query = f"""
        SELECT
          segments.offer_id,
          metrics.impressions,
          metrics.clicks,
          metrics.ctr
        FROM MerchantPerformanceView
        WHERE segments.program = 'FREE_PRODUCT_LISTING'
          AND segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
    """

    url = f"https://shoppingcontent.googleapis.com/content/v2.1/{MERCHANT_ID}/reports/search"
    payload = {"query": query.strip(), "pageSize": 5000}

    perf = {}
    page_token = None

    while True:
        if page_token:
            payload["pageToken"] = page_token
        r = http_requests.post(url, headers=headers, json=payload, timeout=30)
        if not r.ok:
            print(f"  [rotation] Performance fetch error {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
        for row in data.get("results", []):
            offer_id   = row.get("segments", {}).get("offerId", "")
            impressions = int(row.get("metrics", {}).get("impressions", 0) or 0)
            clicks      = int(row.get("metrics", {}).get("clicks", 0) or 0)
            ctr         = float(row.get("metrics", {}).get("ctr", 0.0) or 0.0)
            if offer_id:
                if offer_id not in perf:
                    perf[offer_id] = {"impressions": 0, "clicks": 0, "ctr": 0.0}
                perf[offer_id]["impressions"] += impressions
                perf[offer_id]["clicks"]      += clicks
        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # Recalculate aggregate CTR from summed impressions/clicks
    for oid, m in perf.items():
        if m["impressions"] > 0:
            m["ctr"] = m["clicks"] / m["impressions"]

    print(f"  [rotation] Performance data: {len(perf)} offer_ids with free listing data")
    return perf


# ── Rotation logic ────────────────────────────────────────────────────────────

def get_product_ctr(perf_data: dict, variants: list) -> float:
    """
    Get aggregate CTR for a product by summing across all its variant offer_ids.
    Returns 0.0 if no data yet.
    """
    total_impressions = 0
    total_clicks      = 0
    for v in variants:
        vid = str(v.get("id", ""))
        if vid in perf_data:
            total_impressions += perf_data[vid]["impressions"]
            total_clicks      += perf_data[vid]["clicks"]
    if total_impressions == 0:
        return 0.0
    return total_clicks / total_impressions


def decide_rotation(handle: str, category: str, variants: list,
                    perf_data: dict, state: dict, today: str) -> tuple[int, str]:
    """
    Core rotation decision for one product.

    Returns: (prefix_idx, reason_str)
    Mutates state["products"][handle] in-place.
    """
    today_dt = datetime.strptime(today, "%Y-%m-%d").date()
    pool_size = len(ROTATION_POOLS.get(category, [1]))  # fallback size 1

    # Initialise state for new products
    if handle not in state["products"]:
        state["products"][handle] = {
            "current_prefix_idx": 0,
            "last_rotated":       None,
            "locked":             False,
            "locked_since":       None,
            "lock_streak":        0,
            "history":            [],
        }

    prod = state["products"][handle]
    current_idx = prod["current_prefix_idx"]
    ctr = get_product_ctr(perf_data, variants)

    # ── LOCKED: high performer — hold current prefix ──────────────────────────
    if prod["locked"]:
        if ctr < UNLOCK_CTR:
            # Performance degraded — unlock and rotate
            prod["locked"]      = False
            prod["locked_since"] = None
            prod["lock_streak"] = 0
            new_idx = (current_idx + 1) % pool_size
            prod["current_prefix_idx"] = new_idx
            prod["last_rotated"]       = today
            _append_history(prod, today, new_idx, ctr)
            return new_idx, f"UNLOCKED+ROTATED (CTR {ctr:.3f} fell below {UNLOCK_CTR:.3f})"
        else:
            # Still performing well — hold
            return current_idx, f"LOCKED (CTR {ctr:.3f} >= {LOCK_CTR_THRESHOLD:.3f})"

    # ── Check if this title should be locked (consecutive high CTR) ────────────
    if ctr >= LOCK_CTR_THRESHOLD:
        prod["lock_streak"] = prod.get("lock_streak", 0) + 1
        if prod["lock_streak"] >= LOCK_MIN_DAYS:
            prod["locked"]       = True
            prod["locked_since"] = today
            return current_idx, f"NEWLY LOCKED (CTR {ctr:.3f} for {prod['lock_streak']} days)"
    else:
        prod["lock_streak"] = 0  # reset streak if CTR dips

    # ── COOLING: rotated too recently — wait ──────────────────────────────────
    if prod["last_rotated"]:
        last_dt     = datetime.strptime(prod["last_rotated"], "%Y-%m-%d").date()
        days_since  = (today_dt - last_dt).days
        if days_since < COOLDOWN_DAYS:
            remaining = COOLDOWN_DAYS - days_since
            return current_idx, f"COOLING ({remaining}d left, CTR {ctr:.3f})"

    # ── ROTATE: advance to next prefix ────────────────────────────────────────
    new_idx = (current_idx + 1) % pool_size
    prod["current_prefix_idx"] = new_idx
    prod["last_rotated"]       = today
    _append_history(prod, today, new_idx, ctr)
    return new_idx, f"ROTATED {current_idx}→{new_idx} (CTR {ctr:.3f})"


def _append_history(prod: dict, today: str, idx: int, ctr: float) -> None:
    entry = {"date": today, "prefix_idx": idx, "ctr_at_rotation": round(ctr, 4)}
    prod.setdefault("history", []).append(entry)
    prod["history"] = prod["history"][-30:]  # keep last 30 events


# ── Public API: drop-in replacement for PREFIX_MAP lookup ─────────────────────

def get_rotated_prefix(handle: str, category: str, variants: list,
                        perf_data: dict, state: dict, today: str,
                        gsm: str = "") -> tuple[str, str]:
    """
    Returns (prefix_string, reason) for use in build_optimised_title().

    This replaces the static PREFIX_MAP[category] lookup. Pass the result
    directly into the title builder.
    """
    pool = ROTATION_POOLS.get(category)
    if not pool:
        # Unknown category — fall through to static default
        return f"Premium Streetwear Apparel", "NO_POOL"

    idx, reason = decide_rotation(handle, category, variants, perf_data, state, today)
    prefix = pool[idx]
    if gsm:
        prefix = f"{prefix} {gsm}"
    return prefix, reason
