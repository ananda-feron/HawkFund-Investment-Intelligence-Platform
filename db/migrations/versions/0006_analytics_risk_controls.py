"""Add effective-dated classifications and immutable risk-control evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_analytics_risk_controls"
down_revision: str | None = "0005_market_data_valuation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrument_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sector", sa.String(80), nullable=False),
        sa.Column("asset_class", sa.String(80), nullable=False),
        sa.Column("geography", sa.String(80), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_classification_range",
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("instrument_id", "effective_from", name="uq_classification_effective"),
    )
    op.create_index(
        "ix_classification_cutoff",
        "instrument_classifications",
        ["instrument_id", sa.text("effective_from DESC")],
    )
    op.create_table(
        "risk_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint("version > 0", name="ck_risk_policy_version"),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_risk_policy_range"
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("fund_id", "name", "version", name="uq_risk_policy_version"),
    )
    op.create_table(
        "risk_policy_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_key", sa.String(160), nullable=False),
        sa.Column("operator", sa.String(8), nullable=False),
        sa.Column("threshold", sa.Numeric(28, 12), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("explanation_template", sa.String(500), nullable=False),
        sa.CheckConstraint("operator IN ('MAX','MIN')", name="ck_risk_policy_operator"),
        sa.CheckConstraint("threshold >= 0", name="ck_risk_policy_rule_threshold"),
        sa.ForeignKeyConstraint(["policy_id"], ["risk_policies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("policy_id", "metric_key", name="uq_risk_policy_rule_metric"),
    )
    op.create_table(
        "risk_evaluations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(input_hash) = 64", name="ck_risk_evaluation_hash"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["risk_policies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("policy_id", "as_of", "input_hash", name="uq_risk_evaluation_input"),
    )
    op.create_table(
        "risk_evaluation_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("observed_value", sa.Numeric(28, 12)),
        sa.Column("threshold", sa.Numeric(28, 12), nullable=False),
        sa.Column("breach_amount", sa.Numeric(28, 12)),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("explanation", sa.String(1000), nullable=False),
        sa.CheckConstraint(
            "status IN ('PASS','BREACH','UNAVAILABLE')", name="ck_risk_evaluation_status"
        ),
        sa.CheckConstraint("threshold >= 0", name="ck_risk_evaluation_threshold"),
        sa.CheckConstraint(
            "breach_amount IS NULL OR breach_amount >= 0", name="ck_risk_evaluation_breach"
        ),
        sa.ForeignKeyConstraint(["evaluation_id"], ["risk_evaluations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rule_id"], ["risk_policy_rules.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("evaluation_id", "rule_id", name="uq_risk_evaluation_rule"),
    )
    op.execute("""
        CREATE FUNCTION protect_risk_evidence() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'risk evaluation evidence is immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER risk_evaluations_immutable
        BEFORE UPDATE OR DELETE ON risk_evaluations
        FOR EACH ROW EXECUTE FUNCTION protect_risk_evidence();
        CREATE TRIGGER risk_evaluation_items_immutable
        BEFORE UPDATE OR DELETE ON risk_evaluation_items
        FOR EACH ROW EXECUTE FUNCTION protect_risk_evidence();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS risk_evaluation_items_immutable ON risk_evaluation_items")
    op.execute("DROP TRIGGER IF EXISTS risk_evaluations_immutable ON risk_evaluations")
    op.execute("DROP FUNCTION IF EXISTS protect_risk_evidence")
    op.drop_table("risk_evaluation_items")
    op.drop_table("risk_evaluations")
    op.drop_table("risk_policy_rules")
    op.drop_table("risk_policies")
    op.drop_index("ix_classification_cutoff", table_name="instrument_classifications")
    op.drop_table("instrument_classifications")
