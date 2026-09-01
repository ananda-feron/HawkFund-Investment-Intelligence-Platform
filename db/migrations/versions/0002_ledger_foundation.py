"""Create the Phase 1 Sprint 1 transaction ledger foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_ledger_foundation"
down_revision: str | None = "0001_phase0_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name="ck_accounts_phase1_usd"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("fund_id", "code", name="uq_accounts_fund_code"),
        sa.UniqueConstraint("id", "fund_id", name="uq_accounts_id_fund"),
    )
    op.create_table(
        "import_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255)),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("parser_version", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("initiated_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("posted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_summary", sa.String(1000)),
        sa.CheckConstraint("length(content_sha256) = 64", name="ck_import_batches_sha256"),
        sa.CheckConstraint(
            "total_count >= 0 AND posted_count >= 0 AND duplicate_count >= 0 "
            "AND rejected_count >= 0 AND conflict_count >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "status IN ('RECEIVED', 'PROCESSING', 'COMPLETED', 'COMPLETED_WITH_ERRORS', 'FAILED')",
            name="ck_import_batches_status",
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["initiated_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "fund_id", "source", "content_sha256", name="uq_import_batches_content"
        ),
    )
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True)),
        sa.Column("transaction_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12)),
        sa.Column("unit_price", sa.Numeric(28, 8)),
        sa.Column("amount", sa.Numeric(28, 4)),
        sa.Column("fees", sa.Numeric(28, 4), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trade_date", sa.Date()),
        sa.Column("settlement_date", sa.Date()),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("normalized_payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reverses_transaction_id", postgresql.UUID(as_uuid=True)),
        sa.Column("correction_command_id", postgresql.UUID(as_uuid=True)),
        sa.Column("description", sa.String(500)),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint("currency = 'USD'", name="ck_transactions_phase1_usd"),
        sa.CheckConstraint("length(normalized_payload_hash) = 64", name="ck_transactions_hash"),
        sa.CheckConstraint("fees >= 0", name="ck_transactions_nonnegative_fees"),
        sa.CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_transactions_quantity"),
        sa.CheckConstraint("unit_price IS NULL OR unit_price > 0", name="ck_transactions_price"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_transactions_amount"),
        sa.CheckConstraint("status IN ('POSTED', 'REVERSED')", name="ck_transactions_status"),
        sa.CheckConstraint(
            "(transaction_type IN ('BUY', 'SELL') AND instrument_id IS NOT NULL "
            "AND quantity IS NOT NULL AND unit_price IS NOT NULL AND amount IS NULL) "
            "OR (transaction_type IN ('CASH_DEPOSIT', 'CASH_WITHDRAWAL') "
            "AND instrument_id IS NULL AND quantity IS NULL AND unit_price IS NULL "
            "AND amount IS NOT NULL AND fees = 0) "
            "OR (transaction_type = 'DIVIDEND' AND instrument_id IS NOT NULL "
            "AND quantity IS NULL AND unit_price IS NULL AND amount IS NOT NULL "
            "AND fees = 0) "
            "OR (transaction_type = 'FEE' AND quantity IS NULL AND unit_price IS NULL "
            "AND amount IS NOT NULL AND fees = 0) "
            "OR (transaction_type = 'OPENING_CASH' AND instrument_id IS NULL "
            "AND quantity IS NULL AND unit_price IS NULL AND amount IS NOT NULL "
            "AND fees = 0) "
            "OR (transaction_type = 'OPENING_POSITION' AND instrument_id IS NOT NULL "
            "AND quantity IS NOT NULL AND amount IS NULL AND fees = 0) "
            "OR (transaction_type = 'REVERSAL' AND instrument_id IS NULL "
            "AND quantity IS NULL AND unit_price IS NULL AND amount IS NULL "
            "AND fees = 0 AND reverses_transaction_id IS NOT NULL)",
            name="ck_transactions_type_fields",
        ),
        sa.CheckConstraint(
            "(transaction_type = 'REVERSAL') = (reverses_transaction_id IS NOT NULL)",
            name="ck_transactions_reversal_reference",
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["account_id", "fund_id"],
            ["accounts.id", "accounts.fund_id"],
            ondelete="RESTRICT",
            name="fk_transactions_account_fund",
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["reverses_transaction_id"], ["transactions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "fund_id", "source", "external_id", name="uq_transactions_source_identity"
        ),
        sa.UniqueConstraint("reverses_transaction_id", name="uq_transactions_one_reversal"),
    )
    op.create_index(
        "ix_transactions_replay_order",
        "transactions",
        ["fund_id", "effective_at", "recorded_at", "id"],
    )
    op.create_index(
        "uq_transactions_opening_cash",
        "transactions",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("transaction_type = 'OPENING_CASH' AND status = 'POSTED'"),
    )
    op.create_index(
        "uq_transactions_opening_position",
        "transactions",
        ["account_id", "instrument_id"],
        unique=True,
        postgresql_where=sa.text("transaction_type = 'OPENING_POSITION' AND status = 'POSTED'"),
    )
    op.execute("""
        CREATE FUNCTION protect_transaction_economics() RETURNS trigger AS $$
        BEGIN
            IF ROW(
                NEW.fund_id, NEW.account_id, NEW.instrument_id, NEW.transaction_type,
                NEW.quantity, NEW.unit_price, NEW.amount, NEW.fees, NEW.currency,
                NEW.effective_at, NEW.recorded_at, NEW.trade_date, NEW.settlement_date,
                NEW.source, NEW.external_id, NEW.normalized_payload_hash,
                NEW.import_batch_id, NEW.created_by_user_id,
                NEW.reverses_transaction_id, NEW.correction_command_id,
                NEW.description, NEW.source_metadata
            ) IS DISTINCT FROM ROW(
                OLD.fund_id, OLD.account_id, OLD.instrument_id, OLD.transaction_type,
                OLD.quantity, OLD.unit_price, OLD.amount, OLD.fees, OLD.currency,
                OLD.effective_at, OLD.recorded_at, OLD.trade_date, OLD.settlement_date,
                OLD.source, OLD.external_id, OLD.normalized_payload_hash,
                OLD.import_batch_id, OLD.created_by_user_id,
                OLD.reverses_transaction_id, OLD.correction_command_id,
                OLD.description, OLD.source_metadata
            ) THEN
                RAISE EXCEPTION 'posted transaction economics are immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER transactions_immutable_economics
        BEFORE UPDATE ON transactions
        FOR EACH ROW EXECUTE FUNCTION protect_transaction_economics();
    """)
    op.create_table(
        "import_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("existing_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("existing_payload_hash", sa.String(64), nullable=False),
        sa.Column("incoming_payload_hash", sa.String(64), nullable=False),
        sa.Column("incoming_payload", postgresql.JSONB(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(existing_payload_hash) = 64", name="ck_conflicts_existing_hash"),
        sa.CheckConstraint("length(incoming_payload_hash) = 64", name="ck_conflicts_incoming_hash"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["existing_transaction_id"], ["transactions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "import_batch_id",
            "source",
            "external_id",
            "incoming_payload_hash",
            name="uq_import_conflicts_evidence",
        ),
    )


def downgrade() -> None:
    op.drop_table("import_conflicts")
    op.execute("DROP TRIGGER transactions_immutable_economics ON transactions")
    op.execute("DROP FUNCTION protect_transaction_economics")
    op.drop_index("uq_transactions_opening_position", table_name="transactions")
    op.drop_index("uq_transactions_opening_cash", table_name="transactions")
    op.drop_index("ix_transactions_replay_order", table_name="transactions")
    op.drop_table("transactions")
    op.drop_table("import_batches")
    op.drop_table("accounts")
