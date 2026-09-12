from dataclasses import dataclass

from app.core.international_compliance.models import ComplianceEvidence, EvidenceSource


@dataclass(frozen=True, slots=True)
class EvidenceConflict:
    field_name: str
    values: tuple[str, ...]


def evidence_for_field(
    evidence: tuple[ComplianceEvidence, ...], field_name: str
) -> tuple[ComplianceEvidence, ...]:
    return tuple(item for item in evidence if item.field_name == field_name)


def verified_evidence_for_field(
    evidence: tuple[ComplianceEvidence, ...], field_name: str
) -> tuple[ComplianceEvidence, ...]:
    return tuple(item for item in evidence_for_field(evidence, field_name) if item.verified)


def detect_conflicts(evidence: tuple[ComplianceEvidence, ...]) -> tuple[EvidenceConflict, ...]:
    grouped: dict[str, set[str]] = {}
    for item in evidence:
        if not item.verified:
            continue
        grouped.setdefault(item.field_name, set()).add(item.value.strip())
    conflicts = [
        EvidenceConflict(field_name=field_name, values=tuple(sorted(values)))
        for field_name, values in grouped.items()
        if len(values) > 1
    ]
    return tuple(sorted(conflicts, key=lambda conflict: conflict.field_name))


def has_verified_supplier_or_manufacturer_evidence(
    evidence: tuple[ComplianceEvidence, ...], field_name: str, value: str
) -> bool:
    accepted_sources = {EvidenceSource.SUPPLIER, EvidenceSource.MANUFACTURER}
    return any(
        item.verified
        and item.field_name == field_name
        and item.value.strip().upper() == value.strip().upper()
        and item.source in accepted_sources
        for item in evidence
    )
