from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum

from app.core.international_compliance.audit import ComplianceAuditResult
from app.core.international_compliance.models import ComplianceInput


@dataclass(frozen=True, slots=True)
class ComplianceLedgerEntry:
    product_id: str
    variant_id: str
    fingerprint: str
    status: str
    reasons: tuple[str, ...]
    expected_hs6: str | None
    current_hs: str | None
    expected_country_of_origin: str | None
    current_country_of_origin: str | None
    recorded_at: str

    @classmethod
    def from_audit(
        cls,
        item: ComplianceInput,
        audit: ComplianceAuditResult,
        *,
        recorded_at: str | None = None,
    ) -> ComplianceLedgerEntry:
        timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
        return cls(
            product_id=item.product_id,
            variant_id=item.variant_id,
            fingerprint=item.fingerprint(),
            status=audit.status.value,
            reasons=audit.reasons,
            expected_hs6=audit.expected_hs6,
            current_hs=audit.current_hs,
            expected_country_of_origin=audit.expected_country_of_origin,
            current_country_of_origin=audit.current_country_of_origin,
            recorded_at=timestamp,
        )


def _json_safe(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def ledger_entries_to_jsonl(entries: Iterable[ComplianceLedgerEntry]) -> str:
    """Serialize immutable audit evidence as deterministic JSON Lines."""
    lines = []
    for entry in entries:
        payload = _json_safe(asdict(entry))
        lines.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return "\n".join(lines) + ("\n" if lines else "")
