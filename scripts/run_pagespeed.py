#!/usr/bin/env python3
"""
PageSpeed CI runner — called by .github/workflows/pagespeed.yml
Runs mobile + desktop audits, writes GitHub Step Summary, exports JSON artifact.
Exits 0 always so the workflow never sends failure emails.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Warn if API key is missing
if not os.getenv("PAGESPEED_API_KEY"):
    print("WARNING: PAGESPEED_API_KEY secret not set.")
    print("  Add it at: https://github.com/LXGNDRY/The_HUB/settings/secrets/actions")
    print("  Get a free key at: https://developers.google.com/speed/docs/insights/v5/get-started")
    print()

# Run audit — catch all errors so the workflow always exits 0
try:
    from agents.pagespeed_agent import run
    results = run()
except Exception as e:
    print(f"PageSpeed audit failed: {e}")
    results = {}

# Write GitHub Actions Step Summary
summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")
if summary_path and results:
    with open(summary_path, "a") as f:
        f.write("## 📊 Legendary Branding — PageSpeed Report\n\n")
        for strategy, r in results.items():
            if not r:
                continue
            s = r["scores"]
            v = r["core_web_vitals"]
            icon = "📱" if strategy == "mobile" else "🖥️"
            f.write(f"### {strategy.upper()} {icon}\n\n")
            f.write("| Metric | Score |\n|--------|-------|\n")
            f.write(f"| 🎯 Performance | **{s['performance']}/100** |\n")
            f.write(f"| 🔍 SEO | **{s['seo']}/100** |\n")
            f.write(f"| ♿ Accessibility | **{s['accessibility']}/100** |\n")
            f.write(f"| ✅ Best Practices | **{s['best_practices']}/100** |\n")
            f.write("\n**Core Web Vitals**\n\n")
            f.write("| Metric | Value |\n|--------|-------|\n")
            f.write(f"| LCP | {v['lcp']} |\n")
            f.write(f"| FCP | {v['fcp']} |\n")
            f.write(f"| CLS | {v['cls']} |\n")
            f.write(f"| INP/TBT | {v['inp']} |\n")
            f.write(f"| Speed Index | {v['speed_index']} |\n")
            f.write(f"| TTFB | {v['ttfb']} |\n")
            f.write(f"| TTI | {v['tti']} |\n")
            if r.get("opportunities"):
                f.write("\n**Top Opportunities**\n\n")
                for opp in r["opportunities"][:5]:
                    f.write(f"- ⚡ {opp['title']} — save ~{opp['savings_ms']}ms\n")
            f.write("\n---\n\n")

# Export JSON artifact
try:
    from agents.pagespeed_agent import run_pagespeed
    artifact = {}
    for strategy in ["mobile", "desktop"]:
        try:
            artifact[strategy] = run_pagespeed(strategy=strategy)
        except Exception as e:
            artifact[strategy] = {"error": str(e)}
            print(f"WARNING: {strategy} artifact export failed: {e}")
    with open("pagespeed_results.json", "w") as f:
        json.dump(artifact, f, indent=2)
    print("Results saved to pagespeed_results.json")
except Exception as e:
    print(f"WARNING: artifact export failed: {e}")

# Always exit 0 — never send failure emails
sys.exit(0)
