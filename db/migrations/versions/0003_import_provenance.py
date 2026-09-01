"""Add durable import-row provenance and audit events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_import_provenance"
down_revision: str | None = "0002_ledger_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "import_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("source_locator", sa.String(255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB()),
        sa.Column("raw_payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True)),
        sa.Column("import_conflict_id", postgresql.UUID(as_uuid=True)),
        sa.Column("error_code", sa.String(64)),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("row_number > 0", name="ck_import_records_positive_row"),
        sa.CheckConstraint("length(raw_payload_hash) = 64", name="ck_import_records_hash"),
        sa.CheckConstraint(
            "status IN ('RECEIVED', 'NORMALIZED', 'POSTED', 'DUPLICATE', 'CONFLICT', 'REJECTED')",
            name="ck_import_records_status",
        ),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transaction_id"], ["transactions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["import_conflict_id"], ["import_conflicts.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("import_batch_id", "row_number", name="uq_import_records_batch_row"),
    )
    op.create_index("ix_import_records_transaction", "import_records", ["transaction_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(80), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
    )
    op.create_index(
        "ix_audit_events_entity", "audit_events", ["entity_type", "entity_id", "occurred_at"]
    )
    op.execute("""
        CREATE FUNCTION protect_final_import_record() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                OR OLD.status IN ('POSTED', 'DUPLICATE', 'CONFLICT', 'REJECTED')
            THEN
                RAISE EXCEPTION 'final import evidence is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER import_records_immutable_when_final
        BEFORE UPDATE OR DELETE ON import_records
        FOR EACH ROW EXECUTE FUNCTION protect_final_import_record();

        CREATE FUNCTION protect_final_import_batch() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                OR OLD.status IN ('COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')
            THEN
                RAISE EXCEPTION 'final import batch is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER import_batches_immutable_when_final
        BEFORE UPDATE OR DELETE ON import_batches
        FOR EACH ROW EXECUTE FUNCTION protect_final_import_batch();

        CREATE FUNCTION protect_append_only_audit() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION protect_append_only_audit();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER audit_events_append_only ON audit_events")
    op.execute("DROP FUNCTION protect_append_only_audit")
    op.execute("DROP TRIGGER import_batches_immutable_when_final ON import_batches")
    op.execute("DROP FUNCTION protect_final_import_batch")
    op.execute("DROP TRIGGER import_records_immutable_when_final ON import_records")
    op.execute("DROP FUNCTION protect_final_import_record")
    op.drop_index("ix_audit_events_entity", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_import_records_transaction", table_name="import_records")
    op.drop_table("import_records")
