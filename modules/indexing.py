"""
modules/indexing.py — Google Web Search Indexing Module

Submits URLs to Google's Indexing API for fast crawling.
Ideal for new product pages, blog posts, or updated content.

Supports:
  - URL_UPDATED (submit for indexing / re-indexing)
  - URL_DELETED (notify Google a URL was removed)
  - Batch submission with quota tracking
  - Sitemap parsing to find all indexable URLs

Requires: Service account with "owner" verification of the site in GSC
          AND the Indexing API enabled in the GCP project.

Note: The Indexing API is officially for JobPosting and BroadcastEvent
structured data, but Google has confirmed it works for any URL.
Quota: 200 requests/day by default.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Literal
import requests

from googleapiclient.discovery import build

logger = logging.getLogger("gcp-bot.indexing")

INDEXING_QUOTA_PER_DAY = 200
SITE_URL = os.getenv("GSC_SITE_URL", "https://legendary-branding.com")
SITEMAP_URL = os.getenv("SITEMAP_URL", "https://legendary-branding.com/sitemap.xml")


class IndexingModule:
    """
    Submits URLs to Google's Web Indexing API.
    """

    def __init__(self, credentials):
        self.credentials = credentials
        self._service = None
        self._submitted_today = 0

    @property
    def service(self):
        if not self._service:
            self._service = build(
                "indexing", "v3",
                credentials=self.credentials,
                cache_discovery=False,
            )
        return self._service

    # ------------------------------------------------------------------
    # Core submission
    # ------------------------------------------------------------------

    def submit_url(
        self,
        url: str,
        action: Literal["URL_UPDATED", "URL_DELETED"] = "URL_UPDATED",
    ) -> dict:
        """
        Submit a single URL to Google's Indexing API.

        Args:
            url:    Full URL to submit (e.g. https://legendary-branding.com/products/hoodie)
            action: "URL_UPDATED" (default) or "URL_DELETED"

        Returns:
            API response dict with urlNotificationMetadata.
        """
        if self._submitted_today >= INDEXING_QUOTA_PER_DAY:
            raise RuntimeError(
                f"Daily quota of {INDEXING_QUOTA_PER_DAY} submissions reached. Try again tomorrow."
            )

        body = {"url": url, "type": action}
        logger.info("[indexing] Submitting %s (%s)...", url, action)

        response = self.service.urlNotifications().publish(body=body).execute()
        self._submitted_today += 1

        logger.info(
            "[indexing] Submitted: %s → %s (quota used today: %d/%d)",
            url, action, self._submitted_today, INDEXING_QUOTA_PER_DAY,
        )
        return response

    def submit_urls_batch(
        self,
        urls: list[str],
        action: Literal["URL_UPDATED", "URL_DELETED"] = "URL_UPDATED",
    ) -> dict:
        """
        Submit a list of URLs in batch (respects daily quota).

        Returns:
            {
                "submitted": [list of submitted URLs],
                "skipped": [list of URLs skipped due to quota],
                "errors": [{"url": ..., "error": ...}],
                "quota_used": int,
            }
        """
        results = {"submitted": [], "skipped": [], "errors": [], "quota_used": 0}

        for url in urls:
            if self._submitted_today >= INDEXING_QUOTA_PER_DAY:
                results["skipped"].append(url)
                logger.warning("[indexing] Quota reached. Skipping: %s", url)
                continue
            try:
                self.submit_url(url, action)
                results["submitted"].append(url)
                results["quota_used"] += 1
            except Exception as e:
                results["errors"].append({"url": url, "error": str(e)})
                logger.error("[indexing] Error submitting %s: %s", url, e)

        logger.info(
            "[indexing] Batch complete. Submitted: %d, Skipped: %d, Errors: %d",
            len(results["submitted"]), len(results["skipped"]), len(results["errors"]),
        )
        return results

    # ------------------------------------------------------------------
    # URL status check
    # ------------------------------------------------------------------

    def get_url_status(self, url: str) -> dict:
        """
        Check the indexing notification metadata for a URL.

        Returns:
            urlNotificationMetadata object from the API.
        """
        logger.info("[indexing] Checking status for: %s", url)
        response = self.service.urlNotifications().getMetadata(url=url).execute()
        return response

    # ------------------------------------------------------------------
    # Sitemap parsing
    # ------------------------------------------------------------------

    def get_urls_from_sitemap(self, sitemap_url: str = None, limit: int = 200) -> list[str]:
        """
        Parse a sitemap.xml and return a list of URLs.

        Args:
            sitemap_url: URL of the sitemap (defaults to SITEMAP_URL env var).
            limit:       Max URLs to return (default 200 = daily quota).

        Returns:
            List of URL strings.
        """
        target = sitemap_url or SITEMAP_URL
        logger.info("[indexing] Fetching sitemap: %s", target)

        resp = requests.get(target, timeout=15)
        resp.raise_for_status()

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)

        # Handle both sitemap index and URL sets
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        urls = []

        # Check if it's a sitemap index (contains <sitemap> elements)
        sitemaps = root.findall("sm:sitemap", ns)
        if sitemaps:
            # It's a sitemap index — recurse into each child sitemap
            for sitemap in sitemaps:
                loc = sitemap.find("sm:loc", ns)
                if loc is not None and len(urls) < limit:
                    child_urls = self.get_urls_from_sitemap(loc.text, limit - len(urls))
                    urls.extend(child_urls)
        else:
            # It's a URL set
            for url_elem in root.findall("sm:url", ns):
                loc = url_elem.find("sm:loc", ns)
                if loc is not None:
                    urls.append(loc.text)
                    if len(urls) >= limit:
                        break

        logger.info("[indexing] Found %d URLs in sitemap.", len(urls))
        return urls[:limit]

    # ------------------------------------------------------------------
    # High-level workflows
    # ------------------------------------------------------------------

    def submit_sitemap_urls(self, sitemap_url: str = None, dry_run: bool = False) -> dict:
        """
        Parse sitemap and submit all URLs for indexing.

        Args:
            sitemap_url: Override sitemap URL.
            dry_run:     If True, return URLs without submitting.
        """
        urls = self.get_urls_from_sitemap(sitemap_url)

        if dry_run:
            logger.info("[indexing] DRY RUN — would submit %d URLs.", len(urls))
            return {"dry_run": True, "urls": urls, "count": len(urls)}

        return self.submit_urls_batch(urls)

    def submit_new_products(self, product_handles: list[str], base_url: str = None) -> dict:
        """
        Submit new product URLs to Google for indexing.

        Args:
            product_handles: Shopify product handles (e.g. ["goat-hoodie", "lb-tee"])
            base_url:        Base store URL (defaults to SITE_URL)
        """
        base = (base_url or SITE_URL).rstrip("/")
        urls = [f"{base}/products/{handle}" for handle in product_handles]
        logger.info("[indexing] Submitting %d product URLs.", len(urls))
        return self.submit_urls_batch(urls)

    def get_quota_status(self) -> dict:
        """Return current quota usage for this session."""
        return {
            "submitted_this_session": self._submitted_today,
            "daily_quota": INDEXING_QUOTA_PER_DAY,
            "remaining": INDEXING_QUOTA_PER_DAY - self._submitted_today,
        }
