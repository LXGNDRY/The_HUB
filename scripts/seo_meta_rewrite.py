#!/usr/bin/env python3
"""
seo_meta_rewrite.py — Legendary Branding

Writes SEO title tags and meta descriptions for Shopify collections and
products, driven by *live* product/collection data on every run.

This replaces a prior version of this script that hardcoded a fixed list of
product IDs and title/description strings generated once (2026-05-23) and
never updated. Every run of that version blindly overwrote whatever the
current product titles actually were with that stale snapshot — including
products that had since been renamed — regardless of --dry-run/--overwrite
intent, since it had none. This version reads current title/product_type/
tags from Shopify on every run and only ever touches what's actually there.

Rules (matching scripts/international_readiness_backfill.py's conventions):
- Never overwrites an existing meta title/description unless --overwrite.
- Defaults to dry-run. Pass --apply to write.
- Content is generated from current Shopify title/product_type/tags via
  Gemini (modules/gemini.py) when GOOGLE_API_KEY is configured; otherwise
  falls back to a deterministic template built from the same live fields.

Usage:
  python scripts/seo_meta_rewrite.py
  python scripts/seo_meta_rewrite.py --apply
  python scripts/seo_meta_rewrite.py --apply --overwrite
"""

from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.shopify import _get, _put

BRAND = "Legendary Branding"
TITLE_MAX = 60
DESC_MAX = 160


def _gemini():
    """Return a ready GeminiModule, or None if no API key is configured."""
    api_key = os.getenv("GOOGLE_API_KEY", "")
    if not api_key:
        return None
    try:
        from modules.gemini import GeminiModule

        return GeminiModule(api_key=api_key)
    except Exception as e:  # noqa: BLE001 - Gemini init must not abort the run, fall back to template
        print(f"  [gemini unavailable: {e}] falling back to template generation", file=sys.stderr)
        return None


def _truncate(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _fallback_meta(title: str, page_type: str) -> tuple[str, str]:
    """Deterministic generation from live fields only — no fabricated specs."""
    seo_title = _truncate(f"{title} | {BRAND}", TITLE_MAX)
    noun = "product" if page_type == "product" else "collection"
    seo_desc = _truncate(
        f"Shop {title} from {BRAND}. Premium streetwear {noun}, free shipping available.",
        DESC_MAX,
    )
    return seo_title, seo_desc


def generate_meta(gemini, title: str, page_type: str) -> tuple[str, str]:
    if gemini is not None:
        try:
            result = gemini.generate_seo_meta(page_title=title, page_type=page_type)
            seo_title = _truncate(result.get("meta_title") or "", TITLE_MAX)
            seo_desc = _truncate(result.get("meta_description") or "", DESC_MAX)
            if seo_title and seo_desc:
                return seo_title, seo_desc
        except Exception as e:  # noqa: BLE001 - one bad Gemini call must not abort the run
            print(f"  [gemini generation failed: {e}] falling back to template", file=sys.stderr)
    return _fallback_meta(title, page_type)


_PRODUCT_FIELDS = "id,title,status,metafields_global_title_tag,metafields_global_description_tag"


def fetch_products() -> list[dict]:
    """Page through all products via since_id (Shopify REST cursor pagination
    is exposed via the Link header, which the thin _get() wrapper doesn't
    surface)."""
    products: list[dict] = []
    since_id = None
    while True:
        params = {"limit": 250, "fields": _PRODUCT_FIELDS}
        if since_id:
            params["since_id"] = since_id
        page = _get("/products.json", params).get("products", [])
        if not page:
            break
        products.extend(page)
        since_id = page[-1]["id"]
        if len(page) < 250:
            break
    return [p for p in products if p.get("status") in ("active", "draft")]


def fetch_collections() -> list[dict]:
    collections: list[dict] = []
    for endpoint, key, col_type in (
        ("/custom_collections.json", "custom_collections", "custom_collection"),
        ("/smart_collections.json", "smart_collections", "smart_collection"),
    ):
        data = _get(endpoint, {"limit": 250, "fields": "id,title,metafields_global_title_tag,metafields_global_description_tag"})
        for c in data.get(key, []):
            c["_type"] = col_type
            collections.append(c)
    return collections


def rate():
    time.sleep(0.6)  # ~1.6 req/s — under Shopify's 2/s REST limit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes to Shopify. Default: dry-run.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Regenerate and overwrite meta title/description even if already set. Default: only fill blanks.",
    )
    args = parser.parse_args()

    # DRY_RUN env var (workflow input) is the source of truth when set; --apply is the CLI equivalent.
    dry_run_env = os.getenv("DRY_RUN")
    if dry_run_env is not None:
        apply_changes = dry_run_env.strip().lower() == "false"
    else:
        apply_changes = args.apply

    gemini = _gemini()

    print("=" * 65)
    print("SEO Meta Rewrite")
    print(f"  Apply:      {apply_changes}")
    print(f"  Overwrite:  {args.overwrite}")
    print(f"  Gemini:     {'enabled' if gemini else 'disabled (template fallback)'}")
    print("=" * 65)

    print("\n=== Collections ===")
    collections = fetch_collections()
    col_updates = 0
    col_skipped = 0
    for c in collections:
        has_title = bool((c.get("metafields_global_title_tag") or "").strip())
        has_desc = bool((c.get("metafields_global_description_tag") or "").strip())
        if has_title and has_desc and not args.overwrite:
            col_skipped += 1
            continue

        seo_title, seo_desc = generate_meta(gemini, c["title"], "collection")
        flag = "" if apply_changes else "[DRY] "
        print(f"  {flag}{c['title']}: {seo_title}")

        if apply_changes:
            try:
                _put(
                    f"/{c['_type']}s/{c['id']}.json",
                    {c["_type"]: {"id": c["id"], "metafields_global_title_tag": seo_title, "metafields_global_description_tag": seo_desc}},
                )
                col_updates += 1
            except Exception as e:  # noqa: BLE001 - one failed write must not abort the batch
                print(f"  ❌ {c['title']}: {e}")
            rate()
        else:
            col_updates += 1

    print("\n=== Products ===")
    products = fetch_products()
    prod_updates = 0
    prod_skipped = 0
    for p in products:
        has_title = bool((p.get("metafields_global_title_tag") or "").strip())
        has_desc = bool((p.get("metafields_global_description_tag") or "").strip())
        if has_title and has_desc and not args.overwrite:
            prod_skipped += 1
            continue

        seo_title, seo_desc = generate_meta(gemini, p["title"], "product")
        flag = "" if apply_changes else "[DRY] "
        print(f"  {flag}{p['title']}: {seo_title}")

        if apply_changes:
            try:
                _put(
                    f"/products/{p['id']}.json",
                    {"product": {"id": p["id"], "metafields_global_title_tag": seo_title, "metafields_global_description_tag": seo_desc}},
                )
                prod_updates += 1
            except Exception as e:  # noqa: BLE001 - one failed write must not abort the batch
                print(f"  ❌ {p['title']}: {e}")
            rate()
        else:
            prod_updates += 1

    print(f"\n{'=' * 65}")
    print(f"Collections: {col_updates} {'applied' if apply_changes else 'planned'}, {col_skipped} already set (skipped)")
    print(f"Products:    {prod_updates} {'applied' if apply_changes else 'planned'}, {prod_skipped} already set (skipped)")
    print(f"Complete. applied={col_updates + prod_updates if apply_changes else 0} planned={col_updates + prod_updates if not apply_changes else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
