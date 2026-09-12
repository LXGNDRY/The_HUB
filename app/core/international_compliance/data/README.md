# Compliance V2 curated supplier evidence

`supplier_evidence.json` is the **only** input that lets Compliance V2 move a
variant out of `REVIEW_REQUIRED`. It is deliberately hand-maintained — the
orchestrator (`app/core/international_compliance/orchestrator.py`) never
derives a supplier product ID from a Shopify title, SKU, vendor string, or
tag. If it's not in this file, it isn't verified.

## Format

```json
{
  "bindings": {
    "gid://shopify/ProductVariant/123456789": "TSHIRT-COTTON-BLK-M"
  },
  "products": {
    "TSHIRT-COTTON-BLK-M": {
      "product_family": "core-tee",
      "garment_type": "t-shirt",
      "construction": "knit",
      "materials": [{"fiber": "cotton", "percentage": 100.0}],
      "manufacturing_country": "US",
      "gender_category": "unisex",
      "intended_use": "apparel",
      "subtype": "short-sleeve",
      "weight_grams": 180.0,
      "evidence": [
        {
          "field_name": "manufacturing_country",
          "value": "US",
          "source": "supplier",
          "source_reference": "Supplier COO cert #1234, 2026-01-15",
          "verified": true
        },
        {
          "field_name": "materials",
          "value": "cotton:100",
          "source": "manufacturer",
          "source_reference": "Mill fabric spec sheet, batch 2026-Q1",
          "verified": true
        }
      ]
    }
  }
}
```

## Rules

- **`bindings`** maps a Shopify variant GID (`gid://shopify/ProductVariant/...`)
  to a `supplier_product_id` key in `products`. One binding per variant that's
  ready for classification. Variants with no binding stay `REVIEW_REQUIRED`
  forever — that's correct, not a bug.
- **`products[*].evidence`** is what actually unlocks classification. The
  classifier (`classifier.py`) requires `manufacturing_country` to have at
  least one **verified** evidence entry from `source: "supplier"` or
  `"manufacturer"` — a plain field value with no evidence entry is not enough.
- **`materials`** must sum to ~100% and (for the two rules that exist today)
  be a single fiber at ≥99% to match `knit_cotton_tshirt_or_tank` /
  `knit_cotton_sweater_sweatshirt_hoodie`. Anything else (blends, non-cotton,
  unmodeled garment types) will classify as `UNKNOWN` /
  `unsupported_or_ambiguous_classification` until a new rule is added to
  `classifier.py`'s `_RULES` tuple.
- Never paraphrase or guess a value here to "get past" `REVIEW_REQUIRED`.
  Every field must trace back to a real supplier spec, COO certificate, or
  manufacturer document — that's the entire point of the V2 evidence model.

## How this gets used

- `scripts/compliance_v2_audit.py` (and the nightly `compliance_v2_audit_job`)
  loads this file, evaluates every live Shopify variant, and reports which
  ones are `READY` vs `REVIEW_REQUIRED` and why. It never writes to Shopify.
- `scripts/compliance_v2_apply.py` is the only path that writes HS
  code/country of origin to Shopify, and only for variants the audit marked
  `READY`, and only after an explicit `--approved-by` / `--approval-reference`
  human sign-off matched against the exact planned values.
