"""Import every mapped model so Alembic sees complete metadata."""

from app.models.identity import Membership, User
from app.models.jobs import JobRun
from app.models.security import CredentialReference, MutationAudit, WebhookReceipt
from app.models.subscription import AutomationJob, SubscriptionEvent
from app.models.tenant import Tenant

__all__ = [
    "AutomationJob",
    "CredentialReference",
    "JobRun",
    "Membership",
    "MutationAudit",
    "SubscriptionEvent",
    "Tenant",
    "User",
    "WebhookReceipt",
]
