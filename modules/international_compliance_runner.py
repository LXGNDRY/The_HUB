"""
modules/international_compliance_runner.py — Shopify catalog <-> Compliance V2 wiring.

This is the missing piece that actually runs app/core/international_compliance/
against the live Shopify catalog. It is intentionally read-only: it fetches
every variant, evaluates it through the V2 orchestrator, and reports the
result. It never writes to Shopify — see scripts/compliance_v2_apply.py for
the human-approval-gated write path.

Supplier evidence comes from two places, neither of which is Shopify
title/tag/vendor inference — the orchestrator explicitly forbids that:

1. Auto-detected Printful bindings: if a product carries the `printful.is_synced`
   metafield (written by the real Printful sync integration), its catalog
   product ID and per-variant color are read directly from Shopify and used to
   fetch real manufacturer specs from Printful's public catalog API
   (see suppliers/printful.py). This unlocks material/HS6 verification
   automatically, but manufacturing_country stays unverified/REVIEW_REQUIRED —
   Printful documents multi-country blank sourcing, not one fixed country.
2. A curated, human-maintained JSON file
   (app/core/international_compliance/data/supplier_evidence.json) for
   anything else (non-POD products, or overriding/supplementing the Printful
   auto-detection with real supplier-confirmed facts). Curated bindings always
   take precedence over the Printful auto-detection.

Until real evidence exists for a given variant (via either path), it will
correctly show REVIEW_REQUIRED — that is the fail-closed design working as
intended, not a bug.
"""

import csv
import io
import json
import logging
import os
from dataclasses import dataclass

from app.core.international_compliance.models import (
    ComplianceEvidence,
    EvidenceSource,
    MaterialComponent,
)
from app.core.international_compliance.orchestrator import (
    ComplianceEvaluation,
    SupplierBinding,
    evaluate_variant,
)
from app.core.international_compliance.persistence import plan_compliance_write
from app.core.international_compliance.shopify_catalog import parse_product_node
from app.core.international_compliance.suppliers.base import SupplierComplianceFacts
from app.core.international_compliance.suppliers.printful import PrintfulEvidenceAdapter
from app.core.international_compliance.suppliers.registry import (
    StaticSupplierEvidenceAdapter,
    SupplierRegistry,
)

logger = logging.getLogger("gcp-bot.international_compliance")

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "core", "international_compliance", "data")
_EVIDENCE_PATH = os.path.join(_DATA_DIR, "supplier_evidence.json")

_CURATED_SUPPLIER_NAME = "legendary_curated"

FETCH_VARIANTS_QUERY = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      title
      status
      vendor
      productType
      category { fullName name }
      tags
      printfulSyncMetafield: metafield(namespace: "printful", key: "is_synced") { value }
      variants(first: 100) {
        nodes {
          id
          title
          sku
          taxable
          availableForSale
          selectedOptions { name value }
          inventoryItem {
            id
            requiresShipping
            harmonizedSystemCode
            countryCodeOfOrigin
            measurement { weight { value unit } }
          }
        }
      }
    }
  }
}
"""


def load_supplier_registry(evidence_path: str = _EVIDENCE_PATH):
    """
    Build a SupplierRegistry + shopify-variant-id -> SupplierBinding map from
    the curated evidence file. Returns (registry, bindings_by_variant_id).

    File shape:
      {
        "bindings": {"<shopify_variant_gid>": "<supplier_product_id>", ...},
        "products": {
          "<supplier_product_id>": {
            "product_family": str, "garment_type": str, "construction": str,
            "materials": [{"fiber": str, "percentage": float}, ...],
            "manufacturing_country": str, "gender_category": str,
            "intended_use": str, "subtype": str, "weight_grams": float,
            "evidence": [
              {"field_name": str, "value": str, "source": str,
               "source_reference": str, "verified": bool}, ...
            ]
          }
        }
      }
    """
    if not os.path.exists(evidence_path):
        logger.warning(
            "[international_compliance] No evidence file at %s — every variant "
            "will show REVIEW_REQUIRED until curated supplier facts are added.",
            evidence_path,
        )
        return SupplierRegistry(), {}

    with open(evidence_path) as f:
        raw = json.load(f)

    products: dict[str, SupplierComplianceFacts] = {}
    for product_id, facts in raw.get("products", {}).items():
        materials = tuple(
            MaterialComponent(fiber=m["fiber"], percentage=m["percentage"])
            for m in facts.get("materials", [])
        )
        evidence = tuple(
            ComplianceEvidence(
                field_name=e["field_name"],
                value=e["value"],
                source=EvidenceSource(e["source"]),
                source_reference=e["source_reference"],
                verified=e.get("verified", False),
            )
            for e in facts.get("evidence", [])
        )
        products[product_id] = SupplierComplianceFacts(
            supplier=_CURATED_SUPPLIER_NAME,
            supplier_product_id=product_id,
            product_family=facts.get("product_family"),
            garment_type=facts.get("garment_type"),
            construction=facts.get("construction"),
            materials=materials,
            manufacturing_country=facts.get("manufacturing_country"),
            gender_category=facts.get("gender_category"),
            intended_use=facts.get("intended_use"),
            subtype=facts.get("subtype"),
            weight_grams=facts.get("weight_grams"),
            evidence=evidence,
        )

    registry = SupplierRegistry()
    if products:
        registry.register(
            StaticSupplierEvidenceAdapter(
                supplier_name=_CURATED_SUPPLIER_NAME,
                products=products,
            )
        )
    registry.register(PrintfulEvidenceAdapter())

    bindings_by_variant: dict[str, SupplierBinding] = {}
    for variant_id, supplier_product_id in raw.get("bindings", {}).items():
        bindings_by_variant[variant_id] = SupplierBinding(
            supplier_name=_CURATED_SUPPLIER_NAME,
            supplier_product_id=supplier_product_id,
        )

    return registry, bindings_by_variant


def resolve_supplier_binding(record, curated_bindings: dict) -> SupplierBinding | None:
    """Curated bindings always win. Otherwise, auto-detect Printful fulfillment
    from the product's own `printful.is_synced` sync metafield (written by the
    real Printful integration, never guessed from title/tag/vendor).
    """
    curated = curated_bindings.get(record.variant_id)
    if curated is not None:
        return curated

    if record.printful_catalog_product_id:
        supplier_product_id = record.printful_catalog_product_id
        if record.variant_color:
            supplier_product_id = f"{supplier_product_id}:{record.variant_color}"
        return SupplierBinding(supplier_name="printful", supplier_product_id=supplier_product_id)

    return None


def fetch_all_variant_records():
    """Paginate the full Shopify catalog and return a list of ShopifyVariantRecord."""
    from modules.shopify import _graphql

    records = []
    cursor = None
    while True:
        data = _graphql(FETCH_VARIANTS_QUERY, {"cursor": cursor})
        page = data["data"]["products"]
        for product_node in page["nodes"]:
            records.extend(parse_product_node(product_node))
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return records


@dataclass(frozen=True, slots=True)
class AuditReport:
    total_variants: int
    ready_count: int
    review_required_count: int
    reason_counts: dict
    planned_writes: tuple
    evaluations: tuple

    def summary_lines(self) -> list:
        lines = [
            f"Variants evaluated: {self.total_variants}",
            f"READY (evidence-verified): {self.ready_count}",
            f"REVIEW_REQUIRED: {self.review_required_count}",
            f"Planned writes pending approval: {len(self.planned_writes)}",
        ]
        if self.reason_counts:
            lines.append("Top blocking reasons:")
            for reason, count in sorted(self.reason_counts.items(), key=lambda kv: -kv[1])[:10]:
                lines.append(f"  {reason}: {count}")
        return lines

    def to_csv(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "product_id", "variant_id", "title", "sku", "review_state",
            "confidence", "expected_hs6", "current_hs6",
            "expected_coo", "current_coo", "reasons",
        ])
        for ev in self.evaluations:
            item, decision = ev.item, ev.decision
            writer.writerow([
                item.product_id,
                item.variant_id,
                item.title,
                "",
                decision.review_state.value,
                decision.confidence.value,
                decision.hs6 or "",
                ev.audit.current_hs or "",
                decision.country_of_origin or "",
                ev.audit.current_country_of_origin or "",
                ";".join(decision.reasons),
            ])
        return buf.getvalue()


def run_audit(destinations: tuple = ()) -> AuditReport:
    """Fetch the live catalog and evaluate every variant through Compliance V2. Read-only."""
    registry, bindings = load_supplier_registry()
    records = fetch_all_variant_records()

    evaluations: list[ComplianceEvaluation] = []
    planned_writes = []
    reason_counts: dict = {}
    ready_count = 0

    for record in records:
        binding = resolve_supplier_binding(record, bindings)
        evaluation = evaluate_variant(
            record,
            registry=registry,
            supplier_binding=binding,
            destinations=destinations,
        )
        evaluations.append(evaluation)

        if evaluation.decision.review_state.value == "ready":
            ready_count += 1
        for reason in evaluation.decision.reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        for reason in evaluation.orchestration_reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        plan = plan_compliance_write(
            inventory_item_id=record.inventory_item_id,
            item=evaluation.item,
            current=record.compliance,
        )
        if plan is not None:
            planned_writes.append(plan)

    return AuditReport(
        total_variants=len(records),
        ready_count=ready_count,
        review_required_count=len(records) - ready_count,
        reason_counts=reason_counts,
        planned_writes=tuple(planned_writes),
        evaluations=tuple(evaluations),
    )
