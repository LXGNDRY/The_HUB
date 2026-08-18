"""
modules/sheets.py — Google Sheets Module

Exports live bot data (GA4, GSC, billing, pagespeed) to a Google Sheets
dashboard. Creates and updates sheets automatically.

Requires: Service account credentials with Google Sheets API + Drive API
          enabled. The SA must have editor access to the target sheet.

Env vars:
  SHEETS_DASHBOARD_ID  — Spreadsheet ID to write to (optional; creates new if absent)
"""

import os
import logging
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger("gcp-bot.sheets")

SHEETS_DASHBOARD_ID = os.getenv("SHEETS_DASHBOARD_ID", "")


class SheetsModule:
    """
    Manages a Google Sheets dashboard for the GCP Bot.
    Reads/writes data via the Sheets v4 API.
    """

    def __init__(self, credentials):
        # Attach quota project so Drive/Sheets API calls are billed to the
        # correct GCP project and the SA has permission to make the calls.
        try:
            self.credentials = credentials.with_quota_project("idx-lngndny")
        except AttributeError:
            self.credentials = credentials
        self._sheets_svc = None
        self._drive_svc = None

    @property
    def sheets(self):
        if not self._sheets_svc:
            self._sheets_svc = build("sheets", "v4", credentials=self.credentials, cache_discovery=False)
        return self._sheets_svc

    @property
    def drive(self):
        if not self._drive_svc:
            self._drive_svc = build("drive", "v3", credentials=self.credentials, cache_discovery=False)
        return self._drive_svc

    # ------------------------------------------------------------------
    # Spreadsheet management
    # ------------------------------------------------------------------

    def create_dashboard(self, title: str = "Legendary Branding — GCP Bot Dashboard") -> str:
        """
        Create a new Google Sheets dashboard with all required tabs.
        Returns the spreadsheet ID.
        """
        sheets_to_create = [
            "GA4 Traffic",
            "GSC Performance",
            "PageSpeed",
            "Billing",
            "Quota Monitoring",
            "Log",
        ]
        body = {
            "properties": {"title": title},
            "sheets": [
                {"properties": {"title": name}} for name in sheets_to_create
            ],
        }
        resp = self.sheets.spreadsheets().create(body=body, fields="spreadsheetId").execute()
        spreadsheet_id = resp["spreadsheetId"]
        logger.info("[sheets] Created dashboard: %s (id=%s)", title, spreadsheet_id)
        return spreadsheet_id

    def get_or_create_dashboard(self) -> str:
        """
        Returns SHEETS_DASHBOARD_ID if set.
        If not set, raises an error with setup instructions instead of attempting
        to create a spreadsheet (which requires elevated Drive permissions).
        """
        if SHEETS_DASHBOARD_ID:
            return SHEETS_DASHBOARD_ID
        raise ValueError(
            "SHEETS_DASHBOARD_ID is not configured. "
            "Setup: 1) Create a Google Sheet manually at https://sheets.google.com, "
            "2) Share it with the SA: 901935277314-compute@developer.gserviceaccount.com (Editor access), "
            "3) Copy the spreadsheet ID from the URL (the long string between /d/ and /edit), "
            "4) Set it as the SHEETS_DASHBOARD_ID GitHub secret and redeploy."
        )

    def get_sheet_id(self, spreadsheet_id: str, sheet_name: str) -> int | None:
        """Return the numeric sheetId for a named sheet tab."""
        meta = self.sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        for sheet in meta.get("sheets", []):
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]
        return None

    def ensure_sheet_exists(self, spreadsheet_id: str, sheet_name: str) -> int:
        """Create a sheet tab if it doesn't exist. Returns sheet ID."""
        sheet_id = self.get_sheet_id(spreadsheet_id, sheet_name)
        if sheet_id is not None:
            return sheet_id
        body = {"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]}
        resp = self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        return resp["replies"][0]["addSheet"]["properties"]["sheetId"]

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def write_rows(self, spreadsheet_id: str, sheet_name: str, rows: list[list[Any]],
                   start_row: int = 1, clear_first: bool = False):
        """
        Write rows to a sheet starting at A{start_row}.

        Args:
            spreadsheet_id: Target spreadsheet.
            sheet_name:     Tab name.
            rows:           List of rows, each row is a list of cell values.
            start_row:      1-indexed row to start writing at.
            clear_first:    If True, clears the entire sheet before writing.
        """
        range_name = f"'{sheet_name}'!A{start_row}"

        if clear_first:
            self.sheets.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{sheet_name}'",
            ).execute()

        body = {"values": [[str(v) if v is not None else "" for v in row] for row in rows]}
        self.sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            body=body,
        ).execute()
        logger.info("[sheets] Wrote %d rows to %s!%s", len(rows), sheet_name, range_name)

    def append_row(self, spreadsheet_id: str, sheet_name: str, row: list[Any]):
        """Append a single row to the bottom of a sheet."""
        range_name = f"'{sheet_name}'!A1"
        body = {"values": [[str(v) if v is not None else "" for v in row]]}
        self.sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

    def format_header_row(self, spreadsheet_id: str, sheet_name: str):
        """Bold + background-color the first row of a sheet."""
        sheet_id = self.get_sheet_id(spreadsheet_id, sheet_name)
        if sheet_id is None:
            return
        requests = [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.063, "green": 0.047, "blue": 0.071},
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        ]
        self.sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests},
        ).execute()

    # ------------------------------------------------------------------
    # Dashboard update methods — one per data source
    # ------------------------------------------------------------------

    def update_ga4_sheet(self, spreadsheet_id: str, ga4_traffic: dict, ga4_pages: dict):
        """
        Write GA4 traffic + top pages data to the 'GA4 Traffic' tab.
        """
        sheet = "GA4 Traffic"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = [
            ["GA4 Traffic Report", f"Updated: {now}"],
            [],
            ["Metric", "Value"],
            ["Date Range", ga4_traffic.get("date_range", "N/A")],
            ["Total Sessions", ga4_traffic.get("total_sessions", "N/A")],
            ["Total Users", ga4_traffic.get("total_users", "N/A")],
            ["New Users", ga4_traffic.get("new_users", "N/A")],
            ["Avg Session Duration (s)", ga4_traffic.get("avg_session_duration", "N/A")],
            ["Bounce Rate", ga4_traffic.get("bounce_rate", "N/A")],
            [],
            ["Top Pages", "Sessions", "Bounce Rate"],
        ]
        for page in ga4_pages.get("pages", []):
            rows.append([
                page.get("page", ""),
                page.get("sessions", ""),
                page.get("bounce_rate", ""),
            ])

        self.write_rows(spreadsheet_id, sheet, rows, clear_first=True)
        self.format_header_row(spreadsheet_id, sheet)
        logger.info("[sheets] GA4 sheet updated.")

    def update_gsc_sheet(self, spreadsheet_id: str, gsc_data: dict):
        """
        Write GSC search performance data to the 'GSC Performance' tab.
        """
        sheet = "GSC Performance"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = [
            ["GSC Search Performance", f"Updated: {now}"],
            [],
            ["Query", "Clicks", "Impressions", "CTR", "Position"],
        ]
        for row in gsc_data.get("rows", []):
            rows.append([
                row.get("query", ""),
                row.get("clicks", ""),
                row.get("impressions", ""),
                f"{row.get('ctr', 0):.2%}",
                f"{row.get('position', 0):.1f}",
            ])

        self.write_rows(spreadsheet_id, sheet, rows, clear_first=True)
        self.format_header_row(spreadsheet_id, sheet)
        logger.info("[sheets] GSC sheet updated.")

    def update_pagespeed_sheet(self, spreadsheet_id: str, mobile_result: dict, desktop_result: dict):
        """
        Write PageSpeed scores to the 'PageSpeed' tab with historical append.
        """
        sheet = "PageSpeed"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        def s(result, key):
            return result.get("scores", {}).get(key, "N/A")

        def v(result, key):
            return result.get("core_web_vitals", {}).get(key, "N/A")

        # Write headers if sheet is empty
        existing = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet}'!A1"
        ).execute()
        if not existing.get("values"):
            header = ["Timestamp", "Strategy", "Performance", "SEO", "Accessibility",
                      "Best Practices", "LCP", "FCP", "CLS", "TTI", "Speed Index"]
            self.write_rows(spreadsheet_id, sheet, [header])
            self.format_header_row(spreadsheet_id, sheet)

        # Append new rows
        self.append_row(spreadsheet_id, sheet, [
            now, "Mobile",
            s(mobile_result, "performance"), s(mobile_result, "seo"),
            s(mobile_result, "accessibility"), s(mobile_result, "best_practices"),
            v(mobile_result, "lcp"), v(mobile_result, "fcp"),
            v(mobile_result, "cls"), v(mobile_result, "tti"), v(mobile_result, "speed_index"),
        ])
        self.append_row(spreadsheet_id, sheet, [
            now, "Desktop",
            s(desktop_result, "performance"), s(desktop_result, "seo"),
            s(desktop_result, "accessibility"), s(desktop_result, "best_practices"),
            v(desktop_result, "lcp"), v(desktop_result, "fcp"),
            v(desktop_result, "cls"), v(desktop_result, "tti"), v(desktop_result, "speed_index"),
        ])
        logger.info("[sheets] PageSpeed sheet updated.")

    def update_billing_sheet(self, spreadsheet_id: str, billing_data: dict):
        """
        Write billing summary to the 'Billing' tab.
        """
        sheet = "Billing"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = [
            ["GCP Billing Summary", f"Updated: {now}"],
            [],
            ["Field", "Value"],
            ["Billing Account", billing_data.get("billing_account", "N/A")],
            ["Billing Enabled", billing_data.get("billing_enabled", "N/A")],
            ["Note", billing_data.get("note", "N/A")],
        ]
        self.write_rows(spreadsheet_id, sheet, rows, clear_first=True)
        self.format_header_row(spreadsheet_id, sheet)
        logger.info("[sheets] Billing sheet updated.")

    def update_ga4_countries_sheet(self, spreadsheet_id: str, country_data: dict):
        """
        Write GA4 country breakdown to the 'GA4 Countries' tab.
        Shows where international traffic is landing — key for validating ad geo-targeting.
        """
        sheet = "GA4 Countries"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        rows = [
            ["GA4 Traffic by Country", f"Updated: {now}", f"Period: last {country_data.get('period_days', 28)} days"],
            [],
            ["Country", "Sessions", "Conversions", "Conv. Rate %"],
        ]
        for row in country_data.get("countries", []):
            rows.append([
                row.get("country", ""),
                row.get("sessions", 0),
                row.get("conversions", 0),
                row.get("conversion_rate_pct", 0),
            ])

        self.write_rows(spreadsheet_id, sheet, rows, clear_first=True)
        self.format_header_row(spreadsheet_id, sheet)
        logger.info("[sheets] GA4 Countries sheet updated (%d countries).", len(country_data.get("countries", [])))

    def log_event(self, spreadsheet_id: str, event_type: str, message: str):
        """
        Append an event to the 'Log' tab for audit trail.
        """
        sheet = "Log"
        self.ensure_sheet_exists(spreadsheet_id, sheet)

        # Write header if first time
        existing = self.sheets.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet}'!A1"
        ).execute()
        if not existing.get("values"):
            self.write_rows(spreadsheet_id, sheet, [["Timestamp", "Event Type", "Message"]])
            self.format_header_row(spreadsheet_id, sheet)

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        self.append_row(spreadsheet_id, sheet, [now, event_type, message])

    # ------------------------------------------------------------------
    # Full dashboard refresh
    # ------------------------------------------------------------------

    def refresh_full_dashboard(self, ga4_traffic: dict, ga4_pages: dict,
                                gsc_data: dict, mobile_ps: dict, desktop_ps: dict,
                                billing_data: dict, ga4_countries: dict = None) -> str:
        """
        Update all sheets in one call. Returns the spreadsheet URL.
        ga4_countries: optional country breakdown dict from AnalyticsModule.get_country_breakdown()
        """
        spreadsheet_id = self.get_or_create_dashboard()
        self.update_ga4_sheet(spreadsheet_id, ga4_traffic, ga4_pages)
        self.update_gsc_sheet(spreadsheet_id, gsc_data)
        self.update_pagespeed_sheet(spreadsheet_id, mobile_ps, desktop_ps)
        self.update_billing_sheet(spreadsheet_id, billing_data)
        if ga4_countries:
            self.update_ga4_countries_sheet(spreadsheet_id, ga4_countries)
        self.log_event(spreadsheet_id, "DASHBOARD_REFRESH", "Full dashboard refresh completed.")
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
        logger.info("[sheets] Full dashboard refresh complete: %s", url)
        return url
