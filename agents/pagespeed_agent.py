"""
PageSpeed Insights Agent
Fetches Google PageSpeed Insights data for a given URL.
Outputs Core Web Vitals + category scores for mobile & desktop.
"""

import os
import json
import logging
import requests

logger = logging.getLogger("gcp-bot.pagespeed")

PAGESPEED_API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
PAGESPEED_API_KEY = os.getenv("PAGESPEED_API_KEY", "")
TARGET_URL = os.getenv("PAGESPEED_URL", "https://www.legendarybrandingco.com")


def _score_emoji(score: float) -> str:
    if score >= 90: return "🟢"
    if score >= 50: return "🟡"
    return "🔴"


def _ms(value) -> str:
    """Format milliseconds display."""
    try:
        return f"{float(value):.0f} ms"
    except Exception:
        return str(value)


def run_pagespeed(url: str = TARGET_URL, strategy: str = "mobile") -> dict:
    """
    Call PageSpeed Insights API and return parsed results.
    strategy: 'mobile' | 'desktop'
    """
    params = {
        "url": url,
        "strategy": strategy,
        "category": ["performance", "accessibility", "best-practices", "seo"],
    }
    if PAGESPEED_API_KEY:
        params["key"] = PAGESPEED_API_KEY

    logger.info("[pagespeed] Fetching %s (%s)...", url, strategy)
    resp = requests.get(PAGESPEED_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    lhr = data.get("lighthouseResult", {})
    categories = lhr.get("categories", {})
    audits = lhr.get("audits", {})

    def cat_score(key):
        val = categories.get(key, {}).get("score")
        return round(val * 100) if val is not None else "N/A"

    def audit_display(key):
        a = audits.get(key, {})
        dv = a.get("displayValue", "")
        nv = a.get("numericValue", None)
        if dv:
            return dv
        if nv is not None:
            return _ms(nv)
        return "N/A"

    def audit_score(key):
        s = audits.get(key, {}).get("score")
        if s is None: return "N/A"
        return round(s * 100)

    result = {
        "url": url,
        "strategy": strategy,
        "scores": {
            "performance": cat_score("performance"),
            "accessibility": cat_score("accessibility"),
            "best_practices": cat_score("best-practices"),
            "seo": cat_score("seo"),
        },
        "core_web_vitals": {
            "lcp": audit_display("largest-contentful-paint"),
            "fcp": audit_display("first-contentful-paint"),
            "inp": audit_display("interaction-to-next-paint") or audit_display("total-blocking-time"),
            "cls": audit_display("cumulative-layout-shift"),
            "speed_index": audit_display("speed-index"),
            "ttfb": audit_display("server-response-time"),
            "tti": audit_display("interactive"),
        },
        "opportunities": [],
        "diagnostics": [],
    }

    # Top opportunities (failed audits with savings)
    for key, audit in audits.items():
        if audit.get("details", {}).get("type") == "opportunity":
            savings = audit.get("details", {}).get("overallSavingsMs", 0)
            if savings and float(savings) > 100:
                result["opportunities"].append({
                    "title": audit.get("title", key),
                    "savings_ms": round(float(savings)),
                    "score": audit.get("score"),
                })

    result["opportunities"].sort(key=lambda x: x["savings_ms"], reverse=True)

    return result


def format_report(result: dict) -> str:
    """Format PageSpeed result as a human-readable string."""
    s = result["scores"]
    v = result["core_web_vitals"]
    strat = result["strategy"].upper()
    url = result["url"]

    lines = [
        f"📊 *PageSpeed Report — {strat}*",
        f"🌐 URL: {url}",
        "",
        "**Category Scores**",
        f"  {_score_emoji(s['performance'])} Performance:     {s['performance']}/100",
        f"  {_score_emoji(s['seo'])} SEO:             {s['seo']}/100",
        f"  {_score_emoji(s['accessibility'])} Accessibility:   {s['accessibility']}/100",
        f"  {_score_emoji(s['best_practices'])} Best Practices:  {s['best_practices']}/100",
        "",
        "**Core Web Vitals**",
        f"  🖼️  LCP (Largest Contentful Paint): {v['lcp']}",
        f"  ⚡  FCP (First Contentful Paint):   {v['fcp']}",
        f"  📐  CLS (Cumulative Layout Shift):  {v['cls']}",
        f"  🖱️  INP / TBT:                      {v['inp']}",
        f"  🚀  Speed Index:                    {v['speed_index']}",
        f"  🔗  TTFB (Server Response):         {v['ttfb']}",
        f"  ⏱️  Time to Interactive:            {v['tti']}",
    ]

    if result["opportunities"]:
        lines.append("")
        lines.append("**Top Opportunities**")
        for opp in result["opportunities"][:5]:
            lines.append(f"  ⚡ {opp['title']} — save ~{opp['savings_ms']}ms")

    return "\n".join(lines)


def run(url: str = None):
    """Main entry point — runs mobile + desktop and prints results."""
    target = url or TARGET_URL
    results = {}

    for strategy in ["mobile", "desktop"]:
        print(f"\n{'='*60}")
        print(f"Running PageSpeed: {strategy.upper()} — {target}")
        print('='*60)
        try:
            result = run_pagespeed(target, strategy)
            results[strategy] = result
            report = format_report(result)
            print(report)
            print(f"\n[RAW JSON — {strategy.upper()}]")
            print(json.dumps(result, indent=2))
        except Exception as e:
            print(f"ERROR ({strategy}): {e}")
            logger.error("[pagespeed] Failed for %s (%s): %s", target, strategy, e)

    return results


if __name__ == "__main__":
    import sys
    target_url = sys.argv[1] if len(sys.argv) > 1 else TARGET_URL
    run(target_url)
