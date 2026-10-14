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