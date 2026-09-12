"""Central policy gate for autonomous mutations."""

from dataclasses import dataclass

from app.jobs.contracts import JobEnvelope, JobRisk


class MutationPolicyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class MutationPolicy:
    maximum_batch_size: int = 100

    def authorize(self, envelope: JobEnvelope) -> None:
        batch_size = int(envelope.payload.get("batch_size", 1))
        if batch_size < 1 or batch_size > self.maximum_batch_size:
            raise MutationPolicyViolation(
                f"Batch size {batch_size} exceeds policy maximum {self.maximum_batch_size}."
            )
        if envelope.risk == JobRisk.HIGH_IMPACT_MUTATION and envelope.approval_id is None:
            raise MutationPolicyViolation("High-impact mutation requires an approval reference.")
        if envelope.risk != JobRisk.READ_ONLY and not envelope.idempotency_key:
            raise MutationPolicyViolation("Mutation requires an idempotency key.")
