"""
Printful catalog evidence adapter.

Binding is structural, never guessed: a Shopify product's ``printful.is_synced``
metafield is written by the real Printful sync integration and names Printful's
own public catalog product ID for that blank. This adapter fetches Printful's
public, unauthenticated catalog API (https://api.printful.com/products/<id>)
for that exact ID and treats it as manufacturer-supplied specification data —
the same kind of source the curated evidence file cites, just fetched live.

Material composition is real, structured, per-color data straight from
Printful's catalog (`variant["material"]`) — not parsed out of marketing copy.
It is added as *verified* MANUFACTURER evidence.

Country of origin is deliberately NOT verified here. Printful publishes country
sourcing for a blank product as a list of several countries (the actual
facility varies per order), so no single verified claim is possible from this
source. We still surface a candidate value (the first country Printful lists)
so a human reviewer has a starting point, but it is attached as *unverified*
evidence — the classifier requires verified supplier/manufacturer evidence for
manufacturing_country, so this alone can never move a variant to READY. Getting
a real answer requires either a written sourcing statement from Printful for
this account, or per-shipment fulfillment records.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.core.international_compliance.models import (
    ComplianceEvidence,
    EvidenceSource,
    MaterialComponent,
)
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts
from app.core.international_compliance.suppliers.registry import (
    UnknownSupplierProductError,
)

logger = logging.getLogger("gcp-bot.international_compliance.printful")

_CATALOG_URL = "https://api.printful.com/products/{catalog_id}"

_GARMENT_TYPE_BY_PRINTFUL_TYPE = {
    "T-SHIRT": "t-shirt",
    "TANK-TOP": "tank top",
    "HOODIE": "hoodie",
    "SWEATSHIRT": "sweatshirt",
}

# All garment types this adapter maps to are knit apparel (tees/tanks/hoodies).
_CONSTRUCTION = "knit"


def _parse_supplier_product_id(supplier_product_id: str) -> tuple[str, str | None]:
    """'<catalog_id>' or '<catalog_id>:<color>' -> (catalog_id, color|None)."""
    parts = supplier_product_id.split(":", 1)
    catalog_id = parts[0].strip()
    color = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    return catalog_id, color


@dataclass(slots=True)
class PrintfulEvidenceAdapter:
    """SupplierEvidenceAdapter backed by Printful's public catalog API."""

    _cache: dict | None = None

    def __post_init__(self) -> None:
        if self._cache is None:
            self._cache = {}

    @property
    def supplier_name(self) -> str:
        return "printful"

    def _fetch_catalog_product(self, catalog_id: str) -> dict:
        if catalog_id in self._cache:
            return self._cache[catalog_id]

        import requests

        url = _CATALOG_URL.format(catalog_id=catalog_id)
        for attempt in range(3):
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                data = resp.json()["result"]
                self._cache[catalog_id] = data
                return data
            except Exception as exc:  # noqa: BLE001 - fail closed, never raise into classifier
                logger.warning(
                    "[printful] catalog fetch failed for product %s (attempt %d/3): %s",
                    catalog_id, attempt + 1, exc,
                )
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise UnknownSupplierProductError(catalog_id)

    def fetch_compliance_facts(self, supplier_product_id: str) -> SupplierComplianceFacts:
        catalog_id, color = _parse_supplier_product_id(supplier_product_id)
        catalog = self._fetch_catalog_product(catalog_id)
        product = catalog.get("product") or {}
        variants = catalog.get("variants") or []

        garment_type = _GARMENT_TYPE_BY_PRINTFUL_TYPE.get(str(product.get("type") or "").upper())

        matched = None
        if color:
            matched = next(
                (v for v in variants if str(v.get("color") or "").strip().lower() == color.lower()),
                None,
            )
        if matched is None:
            # No color match (or no color on this product) — fall back to the
            # first variant's material only when every variant shares the same
            # composition, otherwise leave materials empty so the classifier
            # fails closed rather than guessing which color this SKU is.
            distinct_materials = {
                tuple(sorted((m.get("name"), m.get("percentage")) for m in v.get("material") or []))
                for v in variants
            }
            if len(distinct_materials) == 1 and variants:
                matched = variants[0]

        materials: tuple[MaterialComponent, ...] = ()
        evidence: list[ComplianceEvidence] = []
        source_ref = f"Printful public catalog API, product {catalog_id}, fetched live"

        if matched is not None:
            raw_materials = matched.get("material") or []
            materials = tuple(
                MaterialComponent(fiber=str(m["name"]), percentage=float(m["percentage"]))
                for m in raw_materials
            )
            if materials:
                composition_str = ", ".join(f"{m.fiber}:{m.percentage}" for m in materials)
                evidence.append(
                    ComplianceEvidence(
                        field_name="materials",
                        value=composition_str,
                        source=EvidenceSource.MANUFACTURER,
                        source_reference=source_ref,
                        verified=True,
                    )
                )

        sourcing_countries = _extract_sourcing_countries(product.get("description") or "")
        manufacturing_country = sourcing_countries[0] if sourcing_countries else None
        if manufacturing_country:
            evidence.append(
                ComplianceEvidence(
                    field_name="manufacturing_country",
                    value=manufacturing_country,
                    source=EvidenceSource.MANUFACTURER,
                    source_reference=(
                        f"{source_ref} — UNVERIFIED candidate only. Printful lists "
                        f"multiple blank-sourcing countries ({', '.join(sourcing_countries)}); "
                        "the actual facility varies per order. Requires a written "
                        "sourcing statement from Printful, or per-shipment records, "
                        "before this can be treated as verified."
                    ),
                    verified=False,
                )
            )

        return SupplierComplianceFacts(
            supplier=self.supplier_name,
            supplier_product_id=supplier_product_id,
            garment_type=garment_type,
            construction=_CONSTRUCTION if garment_type else None,
            materials=materials,
            manufacturing_country=manufacturing_country,
            evidence=tuple(evidence),
        )


def _extract_sourcing_countries(description: str) -> tuple[str, ...]:
    """Pull the 'Blank product sourced from X, Y, Z' line out of Printful's
    published product description. Returns () if that line isn't present —
    never guesses.
    """
    marker = "blank product sourced from"
    lower = description.lower()
    idx = lower.find(marker)
    if idx == -1:
        return ()
    line_end = description.find("\n", idx)
    line = description[idx + len(marker):line_end if line_end != -1 else None]
    countries = tuple(c.strip().rstrip(".") for c in line.split(",") if c.strip())
    return countries
