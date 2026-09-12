"""
SEO service — indexing, PageSpeed, meta rewrite, robots.txt.
"""


class SEOService:
    """SEO automation — indexing, PageSpeed, meta tags, robots.txt."""

    @staticmethod
    def request_indexing(url: str) -> dict:
        """Request Google Indexing API for a URL."""
        import sys, os
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        import modules.indexing as indexing_mod
        return indexing_mod.request_indexing(url)

    @staticmethod
    def run_pagespeed(url: str, strategy: str = "mobile") -> dict:
        """Run PageSpeed Insights and return scores."""
        import sys, os
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        from agents.pagespeed_agent import PageSpeedAgent
        agent = PageSpeedAgent()
        return agent.analyze(url, strategy=strategy)

    @staticmethod
    def generate_meta_rewrite(products: list, template: str) -> list:
        """Generate SEO meta rewrites for a batch of products."""
        import sys, os
        PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        if PROJECT_ROOT not in sys.path:
            sys.path.insert(0, PROJECT_ROOT)
        # Use the existing scripts/seo_meta_rewrite.py logic
        from scripts.seo_meta_rewrite import rewrite_meta
        return rewrite_meta(products, template)