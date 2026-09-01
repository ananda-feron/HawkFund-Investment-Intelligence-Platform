"""Add immutable snapshot revisions and reconciliation evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_snapshots_reconciliation"
down_revision: str | None = "0003_import_provenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True)),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("canonical_input_hash", sa.String(64), nullable=False),
        sa.Column("canonical_state", postgresql.JSONB(), nullable=False),
        sa.Column("applied_transaction_count", sa.Integer(), nullable=False),
        sa.Column("last_applied_transaction_id", postgresql.UUID(as_uuid=True)),
        sa.Column("supersedes_snapshot_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_snapshots_positive_revision"),
        sa.CheckConstraint("applied_transaction_count >= 0", name="ck_snapshots_nonnegative_count"),
        sa.CheckConstraint("length(canonical_input_hash) = 64", name="ck_snapshots_hash"),
        sa.CheckConstraint("status IN ('CURRENT', 'SUPERSEDED')", name="ck_snapshots_status"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["last_applied_transaction_id"], ["transactions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_snapshot_id"], ["portfolio_snapshots.id"], ondelete="RESTRICT"
        ),
    )
    op.create_index(
        "uq_snapshots_fund_revision",
        "portfolio_snapshots",
        ["fund_id", "as_of", "revision"],
        unique=True,
        postgresql_where=sa.text("account_id IS NULL"),
    )
    op.create_index(
        "uq_snapshots_account_revision",
        "portfolio_snapshots",
        ["fund_id", "account_id", "as_of", "revision"],
        unique=True,
        postgresql_where=sa.text("account_id IS NOT NULL"),
    )
    op.create_index(
        "uq_snapshots_current_fund",
        "portfolio_snapshots",
        ["fund_id", "as_of"],
        unique=True,
        postgresql_where=sa.text("account_id IS NULL AND status = 'CURRENT'"),
    )
    op.create_index(
        "uq_snapshots_current_account",
        "portfolio_snapshots",
        ["fund_id", "account_id", "as_of"],
        unique=True,
        postgresql_where=sa.text("account_id IS NOT NULL AND status = 'CURRENT'"),
    )
    op.create_table(
        "snapshot_cash",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(28, 4), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name="ck_snapshot_cash_usd"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("snapshot_id", "account_id", "currency", name="uq_snapshot_cash"),
    )
    op.create_table(
        "snapshot_positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 12), nullable=False),
        sa.Column("total_cost_basis", sa.Numeric(28, 4)),
        sa.Column("average_cost", sa.Numeric(28, 8)),
        sa.Column("cost_basis_status", sa.String(16), nullable=False),
        sa.Column("source_transaction_ids", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_snapshot_position_quantity"),
        sa.CheckConstraint(
            "(cost_basis_status = 'KNOWN' AND total_cost_basis IS NOT NULL "
            "AND average_cost IS NOT NULL) OR "
            "(cost_basis_status = 'UNKNOWN' AND total_cost_basis IS NULL "
            "AND average_cost IS NULL)",
            name="ck_snapshot_position_basis_status",
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "snapshot_id", "account_id", "instrument_id", name="uq_snapshot_position"
        ),
    )
    op.create_table(
        "reconciliation_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reported_value", sa.Numeric(28, 12), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("import_batch_id", postgresql.UUID(as_uuid=True)),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'USD'", name="ck_reconciliation_observation_usd"),
        sa.CheckConstraint(
            "(kind = 'CASH' AND instrument_id IS NULL) OR "
            "(kind = 'POSITION' AND instrument_id IS NOT NULL AND reported_value >= 0)",
            name="ck_reconciliation_observation_kind",
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "fund_id", "source", "external_id", name="uq_reconciliation_observation_source"
        ),
    )
    op.create_index(
        "ix_reconciliation_observation_cutoff",
        "reconciliation_observations",
        ["fund_id", "as_of", "account_id"],
    )
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tolerance", sa.Numeric(28, 12), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint("tolerance >= 0", name="ck_reconciliation_tolerance"),
        sa.CheckConstraint("length(evidence_hash) = 64", name="ck_reconciliation_evidence_hash"),
        sa.CheckConstraint(
            "status IN ('MATCHED', 'BREACH', 'UNAVAILABLE')",
            name="ck_reconciliation_run_status",
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["portfolio_snapshots.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "snapshot_id", "tolerance", "evidence_hash", name="uq_reconciliation_run"
        ),
    )
    op.create_table(
        "reconciliation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reconciliation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expected_value", sa.Numeric(28, 12), nullable=False),
        sa.Column("reported_value", sa.Numeric(28, 12), nullable=False),
        sa.Column("difference", sa.Numeric(28, 12), nullable=False),
        sa.Column("tolerance", sa.Numeric(28, 12), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('MATCHED', 'BREACH')", name="ck_reconciliation_item_status"),
        sa.ForeignKeyConstraint(
            ["reconciliation_run_id"], ["reconciliation_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["observation_id"], ["reconciliation_observations.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint(
            "reconciliation_run_id", "observation_id", name="uq_reconciliation_item"
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_snapshot_content() RETURNS trigger AS $$
        BEGIN
            IF ROW(
                NEW.fund_id, NEW.account_id, NEW.as_of, NEW.revision,
                NEW.calculation_version, NEW.canonical_input_hash,
                NEW.canonical_state, NEW.applied_transaction_count,
                NEW.last_applied_transaction_id, NEW.supersedes_snapshot_id,
                NEW.created_at
            ) IS DISTINCT FROM ROW(
                OLD.fund_id, OLD.account_id, OLD.as_of, OLD.revision,
                OLD.calculation_version, OLD.canonical_input_hash,
                OLD.canonical_state, OLD.applied_transaction_count,
                OLD.last_applied_transaction_id, OLD.supersedes_snapshot_id,
                OLD.created_at
            ) THEN
                RAISE EXCEPTION 'snapshot content is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER portfolio_snapshots_immutable_content
        BEFORE UPDATE ON portfolio_snapshots
        FOR EACH ROW EXECUTE FUNCTION protect_snapshot_content();

        CREATE FUNCTION protect_derived_evidence() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'derived evidence is immutable';
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER snapshot_cash_immutable
        BEFORE UPDATE OR DELETE ON snapshot_cash
        FOR EACH ROW EXECUTE FUNCTION protect_derived_evidence();

        CREATE TRIGGER snapshot_positions_immutable
        BEFORE UPDATE OR DELETE ON snapshot_positions
        FOR EACH ROW EXECUTE FUNCTION protect_derived_evidence();

        CREATE TRIGGER reconciliation_observations_immutable
        BEFORE UPDATE OR DELETE ON reconciliation_observations
        FOR EACH ROW EXECUTE FUNCTION protect_derived_evidence();

        CREATE TRIGGER reconciliation_runs_immutable
        BEFORE UPDATE OR DELETE ON reconciliation_runs
        FOR EACH ROW EXECUTE FUNCTION protect_derived_evidence();

        CREATE TRIGGER reconciliation_items_immutable
        BEFORE UPDATE OR DELETE ON reconciliation_items
        FOR EACH ROW EXECUTE FUNCTION protect_derived_evidence();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER reconciliation_items_immutable ON reconciliation_items")
    op.execute("DROP TRIGGER reconciliation_runs_immutable ON reconciliation_runs")
    op.execute("DROP TRIGGER reconciliation_observations_immutable ON reconciliation_observations")
    op.execute("DROP TRIGGER snapshot_positions_immutable ON snapshot_positions")
    op.execute("DROP TRIGGER snapshot_cash_immutable ON snapshot_cash")
    op.execute("DROP FUNCTION protect_derived_evidence")
    op.execute("DROP TRIGGER portfolio_snapshots_immutable_content ON portfolio_snapshots")
    op.execute("DROP FUNCTION protect_snapshot_content")
    op.drop_table("reconciliation_items")
    op.drop_table("reconciliation_runs")
    op.drop_index("ix_reconciliation_observation_cutoff", table_name="reconciliation_observations")
    op.drop_table("reconciliation_observations")
    op.drop_table("snapshot_positions")
    op.drop_table("snapshot_cash")
    op.drop_index("uq_snapshots_current_account", table_name="portfolio_snapshots")
    op.drop_index("uq_snapshots_current_fund", table_name="portfolio_snapshots")
    op.drop_index("uq_snapshots_account_revision", table_name="portfolio_snapshots")
    op.drop_index("uq_snapshots_fund_revision", table_name="portfolio_snapshots")
    op.drop_table("portfolio_snapshots")
