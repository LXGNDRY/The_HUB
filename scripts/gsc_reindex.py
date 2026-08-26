#!/usr/bin/env python3
"""
gsc_reindex.py
Re-indexing entry point for Legendary Branding pages in Google Search Console.

Three steps, in order of how much they can actually be trusted:

  A. Sitemap resubmission (searchconsole v1 sitemaps().submit) — the one
     officially supported, ToS-compliant way to ask Google to re-crawl the
     site. This is the real lever.
  B. Best-effort Web Indexing API push (modules.indexing.IndexingModule) —
     that API is officially restricted to JobPosting/BroadcastEvent pages.
     Calling it on product pages is off-label: Google may return HTTP 200
     while silently discarding the submission. Never treat this as proof
     of indexing.
  C. URL Inspection status report — read-only, reports Google's *current*
     view of each URL so the run has a real result to show, not just
     submission counts.

Auth: GCP service account (GCP_SA_KEY), scopes: webmasters (write) +
indexing. Prerequisite: the service account
(g-indexnow@idx-lngndny.iam.gserviceaccount.com) must be a Full/Owner user
on the property in Search Console -> Settings -> Users and permissions.

GSC_TOKEN_JSON (used elsewhere in this repo) is scoped webmasters.readonly
and cannot be used here.

Usage:
  python gsc_reindex.py                          # full run, up to 200 URLs
  python gsc_reindex.py --dry-run                # no submissions, just counts
  python gsc_reindex.py --limit 10                # cap Step B/C URL count
  python gsc_reindex.py --sitemap-url https://legendary-branding.com/sitemap.xml
  python gsc_reindex.py --site-url sc-domain:legendary-branding.com  # skip auto-resolution

Note: the GSC siteUrl is auto-resolved via webmasters.sites.list at runtime
(a Domain property like sc-domain:legendary-branding.com and a URL-prefix
property like https://legendary-branding.com/ are different resources to
the API, so this avoids guessing at the format).
"""
import argparse
import json
import os
import sys
import time

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from modules.indexing import IndexingModule  # noqa: E402

FALLBACK_SITE_URL = "https://legendary-branding.com/"
SITEMAP_URL = "https://legendary-branding.com/sitemap.xml"
SITES_LIST_URL = "https://www.googleapis.com/webmasters/v3/sites"
INSPECT_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"

SCOPES = [
    "https://www.googleapis.com/auth/webmasters",  # write: sitemaps.submit
    "https://www.googleapis.com/auth/indexing",     # Web Indexing API
]


def get_credentials():
    sa_key_json = os.environ.get("GCP_SA_KEY")
    if not sa_key_json:
        print("ERROR: GCP_SA_KEY not set", file=sys.stderr)
        sys.exit(1)
    sa_info = json.loads(sa_key_json)
    print(f"Service account: {sa_info.get('client_email')}")
    print(f"Project ID:      {sa_info.get('project_id')}")
    return service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)


def resolve_site_url(creds):
    """
    Ask Google which GSC properties this service account actually has verified
    access to, and use that exact siteUrl (rather than guessing at the
    URL-prefix vs. sc-domain: form) for all subsequent API calls. A Domain
    property (sc-domain:example.com) and a URL-prefix property
    (https://example.com/) are different resources to the Search Console
    API even when both "cover" the same site — Owner access on one does not
    grant access to the other.
    """
    print("Resolving verified GSC site (webmasters.sites.list)...")
    from google.auth.transport.requests import Request as GoogleRequest
    creds.refresh(GoogleRequest())
    resp = requests.get(
        SITES_LIST_URL,
        headers={"Authorization": f"Bearer {creds.token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"  WARNING: sites.list returned HTTP {resp.status_code} — falling back to {FALLBACK_SITE_URL}")
        return FALLBACK_SITE_URL

    entries = resp.json().get("siteEntry", [])
    if not entries:
        print(f"  WARNING: sites.list returned no properties — falling back to {FALLBACK_SITE_URL}")
        return FALLBACK_SITE_URL

    print(f"  Service account has access to {len(entries)} propert{'y' if len(entries) == 1 else 'ies'}:")
    for entry in entries:
        print(f"    - {entry.get('siteUrl')} (permission: {entry.get('permissionLevel')})")

    for entry in entries:
        site_url = entry.get("siteUrl", "")
        if "legendary-branding.com" in site_url:
            print(f"  Using: {site_url}")
            return site_url

    site_url = entries[0]["siteUrl"]
    print(f"  No legendary-branding.com match found; using first property: {site_url}")
    return site_url


def submit_sitemap(creds, site_url, sitemap_url, dry_run):
    """Step A — the real, ToS-compliant recrawl request."""
    print("=" * 70)
    print("STEP A: Sitemap resubmission (Search Console API)")
    print("=" * 70)
    print(f"  Site:    {site_url}")
    print(f"  Sitemap: {sitemap_url}")

    if dry_run:
        print("  [dry-run] Would call sitemaps().submit() — skipping.")
        return {"status": "dry_run"}

    try:
        service = build("searchconsole", "v1", credentials=creds, cache_discovery=False)
        service.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
        print("  Sitemap resubmitted successfully.")
        print("  This asks Google to re-fetch and re-evaluate the sitemap; crawl")
        print("  timing/priority is still entirely at Google's discretion.")
        return {"status": "submitted"}
    except HttpError as e:
        print(f"  ERROR submitting sitemap: {e}")
        print("  site_url above was resolved from webmasters.sites.list, so this")
        print("  is unlikely to be a property-format mismatch — check that the")
        print("  service account still has Owner/Full access on that property.")
        raise


def submit_web_indexing(creds, urls, dry_run):
    """Step B — best-effort, off-label Web Indexing API push."""
    print()
    print("=" * 70)
    print("STEP B: Best-effort Web Indexing API push [best-effort/off-label]")
    print("=" * 70)
    print("  The Web Indexing API is officially restricted to JobPosting and")
    print("  BroadcastEvent structured data. Submitting product pages is off-label:")
    print("  Google may return HTTP 200 while silently discarding the submission.")
    print("  Do not treat a 'submitted' count below as proof of indexing.")

    idx = IndexingModule(creds)

    if dry_run:
        print(f"  [dry-run] Would submit {len(urls)} URLs — skipping.")
        return {"dry_run": True, "count": len(urls)}

    result = idx.submit_urls_batch(urls, action="URL_UPDATED")
    print(f"  Submitted: {len(result['submitted'])}")
    print(f"  Skipped (quota): {len(result['skipped'])}")
    print(f"  Errors: {len(result['errors'])}")
    for err in result["errors"][:10]:
        print(f"    - {err['url']}: {err['error']}")
    return result


def inspect_urls(creds, site_url, urls):
    """Step C — real, read-only index status per URL."""
    print()
    print("=" * 70)
    print("STEP C: URL Inspection status report")
    print("=" * 70)

    from google.auth.transport.requests import Request as GoogleRequest
    creds.refresh(GoogleRequest())

    headers = {"Authorization": f"Bearer {creds.token}", "Content-Type": "application/json"}
    rows = []
    verdict_counts = {}
    first_error_body = None

    for url in urls:
        payload = {"inspectionUrl": url, "siteUrl": site_url}
        try:
            resp = requests.post(INSPECT_URL, headers=headers, json=payload, timeout=15)
            if resp.status_code != 200:
                if first_error_body is None:
                    first_error_body = resp.text[:500]
                rows.append({"url": url, "verdict": f"HTTP_{resp.status_code}", "coverageState": "", "lastCrawlTime": ""})
                verdict_counts[f"HTTP_{resp.status_code}"] = verdict_counts.get(f"HTTP_{resp.status_code}", 0) + 1
                continue
            data = resp.json()
            result = data.get("inspectionResult", {})
            index_result = result.get("indexStatusResult", {})
            verdict = index_result.get("verdict", "UNKNOWN")
            coverage = index_result.get("coverageState", "")
            last_crawl = index_result.get("lastCrawlTime", "")
            rows.append({"url": url, "verdict": verdict, "coverageState": coverage, "lastCrawlTime": last_crawl})
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        except requests.RequestException as e:
            rows.append({"url": url, "verdict": "ERROR", "coverageState": str(e), "lastCrawlTime": ""})
            verdict_counts["ERROR"] = verdict_counts.get("ERROR", 0) + 1
        time.sleep(1.2)

    print(f"  Inspected {len(rows)} URLs.")
    print("  Verdict breakdown:")
    for verdict, count in sorted(verdict_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {verdict}: {count}")
    if first_error_body:
        print(f"  First error response body: {first_error_body}")

    print()
    print("  Per-URL detail:")
    for row in rows:
        print(f"    [{row['verdict']:20s}] {row['coverageState']:30s} {row['url']}")

    return rows


def main():
    parser = argparse.ArgumentParser(description="Re-index Legendary Branding pages in Google Search Console")
    parser.add_argument("--dry-run", action="store_true", help="Skip real submissions, just report counts")
    parser.add_argument("--limit", type=int, default=200, help="Max URLs for Web Indexing push + Inspection (default 200)")
    parser.add_argument("--sitemap-url", default=SITEMAP_URL, help="Override sitemap URL")
    parser.add_argument("--site-url", default=None, help="Override GSC siteUrl (skips auto-resolution)")
    args = parser.parse_args()

    creds = get_credentials()
    site_url = args.site_url or resolve_site_url(creds)

    sitemap_result = submit_sitemap(creds, site_url, args.sitemap_url, args.dry_run)

    idx = IndexingModule(creds)
    urls = idx.get_urls_from_sitemap(sitemap_url=args.sitemap_url, limit=args.limit)
    print(f"\nLoaded {len(urls)} URLs from live sitemap (limit={args.limit}).")

    web_indexing_result = submit_web_indexing(creds, urls, args.dry_run)
    inspection_rows = inspect_urls(creds, site_url, urls)

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Sitemap resubmission: {sitemap_result.get('status', 'dry_run')}")
    print(f"  URLs processed: {len(urls)}")
    if not args.dry_run:
        print(f"  Web Indexing submitted: {len(web_indexing_result.get('submitted', []))}")
    indexed = sum(1 for r in inspection_rows if r["verdict"] == "PASS")
    print(f"  Currently indexed (Inspection verdict=PASS): {indexed}/{len(inspection_rows)}")

    if sitemap_result.get("status") == "submitted" or args.dry_run:
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
