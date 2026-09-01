"""Add append-only market-data evidence for deterministic valuation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_market_data_valuation"
down_revision: str | None = "0004_snapshots_reconciliation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_identifiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scheme", sa.String(16), nullable=False),
        sa.Column("value", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False, server_default=""),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "scheme IN ('TICKER','FIGI','CUSIP','ISIN','PROVIDER')", name="ck_identifier_scheme"
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_identifier_range",
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("scheme", "value", "provider", name="uq_security_identifier"),
    )
    op.create_index("ix_security_identifier_lookup", "security_identifiers", ["value", "provider"])
    op.create_table(
        "market_data_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflict_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("length(request_hash) = 64", name="ck_market_data_batch_hash"),
        sa.CheckConstraint(
            "status IN ('RECEIVED','COMPLETED','COMPLETED_WITH_CONFLICTS','FAILED')",
            name="ck_market_data_batch_status",
        ),
        sa.CheckConstraint(
            "inserted_count >= 0 AND duplicate_count >= 0 AND conflict_count >= 0",
            name="ck_market_data_batch_counts",
        ),
        sa.UniqueConstraint(
            "provider", "dataset", "request_hash", name="uq_market_data_batch_request"
        ),
    )
    op.create_table(
        "market_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("price_type", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Numeric(28, 8), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source_identifier", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_market_price_positive"),
        sa.CheckConstraint("currency = 'USD'", name="ck_market_price_usd"),
        sa.CheckConstraint("price_type IN ('CLOSE','ADJUSTED_CLOSE')", name="ck_market_price_type"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["batch_id"], ["market_data_batches.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "instrument_id",
            "provider",
            "price_type",
            "observed_at",
            name="uq_market_price_observation",
        ),
    )
    op.create_index(
        "ix_market_price_cutoff",
        "market_prices",
        ["instrument_id", "price_type", sa.text("observed_at DESC")],
    )
    op.create_table(
        "market_price_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("existing_price_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incoming_price", sa.Numeric(28, 8), nullable=False),
        sa.Column("incoming_currency", sa.String(3), nullable=False),
        sa.Column("incoming_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("incoming_price > 0", name="ck_market_price_conflict_positive"),
        sa.CheckConstraint("incoming_currency = 'USD'", name="ck_market_price_conflict_usd"),
        sa.ForeignKeyConstraint(["batch_id"], ["market_data_batches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["existing_price_id"], ["market_prices.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "batch_id", "existing_price_id", "incoming_price", name="uq_market_price_conflict"
        ),
    )
    op.execute("""
        CREATE FUNCTION protect_market_data_evidence() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'market data evidence is immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER market_prices_immutable BEFORE UPDATE OR DELETE ON market_prices
        FOR EACH ROW EXECUTE FUNCTION protect_market_data_evidence();
        CREATE TRIGGER market_price_conflicts_immutable
        BEFORE UPDATE OR DELETE ON market_price_conflicts
        FOR EACH ROW EXECUTE FUNCTION protect_market_data_evidence();
        CREATE TRIGGER security_identifiers_no_delete BEFORE DELETE ON security_identifiers
        FOR EACH ROW EXECUTE FUNCTION protect_market_data_evidence();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS security_identifiers_no_delete ON security_identifiers")
    op.execute("DROP TRIGGER IF EXISTS market_price_conflicts_immutable ON market_price_conflicts")
    op.execute("DROP TRIGGER IF EXISTS market_prices_immutable ON market_prices")
    op.execute("DROP FUNCTION IF EXISTS protect_market_data_evidence")
    op.drop_table("market_price_conflicts")
    op.drop_index("ix_market_price_cutoff", table_name="market_prices")
    op.drop_table("market_prices")
    op.drop_table("market_data_batches")
    op.drop_index("ix_security_identifier_lookup", table_name="security_identifiers")
    op.drop_table("security_identifiers")
