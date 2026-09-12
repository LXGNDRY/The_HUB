from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.international_compliance.models import (
    ClassificationConfidence,
    ClassificationDecision,
    ComplianceInput,
    ReviewState,
)


@dataclass(frozen=True, slots=True)
class ManualReviewResolution:
    hs6: str
    country_of_origin: str
    reviewer: str
    rationale: str
    evidence_reference: str
    reviewed_at: str

    def __post_init__(self) -> None:
        if len(self.hs6) != 6 or not self.hs6.isdigit():
            raise ValueError("hs6 must be exactly six digits")
        coo = self.country_of_origin
        if len(coo) != 2 or not coo.isalpha() or coo != coo.upper():
            raise ValueError("country_of_origin must be uppercase ISO alpha-2")
        for name, value in (
            ("reviewer", self.reviewer),
            ("rationale", self.rationale),
            ("evidence_reference", self.evidence_reference),
            ("reviewed_at", self.reviewed_at),
        ):
            if not value.strip():
                raise ValueError(f"{name} is required")

    @classmethod
    def create(
        cls,
        *,
        hs6: str,
        country_of_origin: str,
        reviewer: str,
        rationale: str,
        evidence_reference: str,
    ) -> ManualReviewResolution:
        return cls(
            hs6=hs6,
            country_of_origin=country_of_origin.upper(),
            reviewer=reviewer,
            rationale=rationale,
            evidence_reference=evidence_reference,
            reviewed_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True, slots=True)
class ReviewedClassification:
    input_fingerprint: str
    decision: ClassificationDecision
    resolution: ManualReviewResolution


def apply_manual_review(
    item: ComplianceInput,
    resolution: ManualReviewResolution,
) -> ReviewedClassification:
    """Promote an explicitly reviewed product to VERIFIED without altering raw evidence.

    Manual approval is deliberately separate from automatic classification. The
    resolution records who approved the customs values and the external evidence
    used, so a future material/origin change invalidates the approval via the
    compliance fingerprint.
    """
    decision = ClassificationDecision(
        hs6=resolution.hs6,
        country_of_origin=resolution.country_of_origin,
        confidence=ClassificationConfidence.VERIFIED,
        review_state=ReviewState.READY,
        reasons=(
            "manual_review_verified",
            f"reviewer:{resolution.reviewer}",
            f"evidence:{resolution.evidence_reference}",
        ),
        rule_version="manual-review-v2",
    )
    return ReviewedClassification(
        input_fingerprint=item.fingerprint(),
        decision=decision,
        resolution=resolution,
    )


def reviewed_classification_is_current(
    item: ComplianceInput,
    reviewed: ReviewedClassification,
) -> bool:
    """A review is valid only for the exact physical/compliance facts reviewed."""
    return reviewed.input_fingerprint == item.fingerprint()
