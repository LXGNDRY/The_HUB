"""Enterprise identity, secret references, replay protection, and audit tables."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_enterprise_security"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    role = sa.Enum("OWNER", "ADMIN", "OPERATOR", "VIEWER", name="membershiprole")
    role.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_subject", sa.String(255), nullable=False, unique=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("role", role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )
    op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "credential_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("secret_resource", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "provider", name="uq_credential_tenant_provider"),
    )
    op.create_index("ix_credential_references_tenant_id", "credential_references", ["tenant_id"])
    op.create_table(
        "webhook_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("event_id", sa.String(255), nullable=False),
        sa.Column("topic", sa.String(255), nullable=False, server_default=""),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("succeeded", sa.Boolean(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=False, server_default=""),
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
    )
    op.create_table(
        "mutation_audits",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("actor_subject", sa.String(255), nullable=False),
        sa.Column("operation", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("before_state", sa.JSON(), nullable=True),
        sa.Column("after_state", sa.JSON(), nullable=True),
        sa.Column("rollback_reference", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "job_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=True),
        sa.Column("kind", sa.String(255), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="claimed"),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Refuse to destroy any credential material that was not migrated first.
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM tenants WHERE COALESCE(shopify_access_token, '') <> ''
            OR COALESCE(gcp_service_account_json, '') <> '' OR COALESCE(klaviyo_api_key, '') <> '')
        THEN RAISE EXCEPTION 'plaintext tenant credentials exist; migrate them before upgrade';
        END IF; END $$;"""
    )
    op.drop_column("tenants", "shopify_access_token")
    op.drop_column("tenants", "gcp_service_account_json")
    op.drop_column("tenants", "klaviyo_api_key")


def downgrade() -> None:
    raise RuntimeError("Security migration downgrade is intentionally blocked; restore from a reviewed backup.")
