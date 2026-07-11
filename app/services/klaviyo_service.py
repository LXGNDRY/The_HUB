"""
Klaviyo service — wraps the existing Klaviyo module.
"""

import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class KlaviyoService:
    """Service layer wrapping the existing Klaviyo module."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key

    def _configure(self):
        if self.api_key:
            os.environ["KLAVIYO_API_KEY"] = self.api_key
        import modules.klaviyo as klaviyo_mod
        return klaviyo_mod

    def get_account_info(self) -> dict:
        klaviyo = self._configure()
        m = klaviyo.KlaviyoModule()
        return m.account_info()

    def get_lists(self) -> dict:
        klaviyo = self._configure()
        return klaviyo.list_lists()

    def get_campaigns(self) -> dict:
        klaviyo = self._configure()
        return klaviyo.list_campaigns()

    def get_metrics(self) -> dict:
        klaviyo = self._configure()
        return klaviyo.list_metrics()

    def get_flows(self) -> dict:
        klaviyo = self._configure()
        return klaviyo.list_flows()

    def get_overview(self) -> dict:
        klaviyo = self._configure()
        m = klaviyo.KlaviyoModule()
        return m.overview()