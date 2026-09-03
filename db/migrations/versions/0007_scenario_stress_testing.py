"""Add versioned scenario definitions, sensitivities, and immutable run evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_scenario_stress_testing"
down_revision: str | None = "0006_analytics_risk_controls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scenario_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint("version > 0", name="ck_scenario_version"),
        sa.CheckConstraint("kind IN ('HYPOTHETICAL','HISTORICAL')", name="ck_scenario_kind"),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("fund_id", "name", "version", name="uq_scenario_version"),
    )
    op.create_table(
        "scenario_shocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target", sa.String(160), nullable=False),
        sa.Column("magnitude", sa.Numeric(28, 12), nullable=False),
        sa.Column("unit", sa.String(24), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("sequence > 0", name="ck_scenario_shock_sequence"),
        sa.CheckConstraint(
            "target_type IN ('SECURITY','MARKET','SECTOR','RATE','FACTOR')",
            name="ck_scenario_shock_target_type",
        ),
        sa.CheckConstraint(
            "unit IN ('RELATIVE_RETURN','YIELD_CHANGE','FACTOR_MOVE')",
            name="ck_scenario_shock_unit",
        ),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_definitions.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("scenario_id", "sequence", name="uq_scenario_shock_sequence"),
    )
    op.create_table(
        "instrument_risk_sensitivities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True)),
        sa.Column("rate_duration", sa.Numeric(28, 12)),
        sa.Column("factor_loadings", postgresql.JSONB(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("source_metadata", postgresql.JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_sensitivity_range",
        ),
        sa.CheckConstraint(
            "rate_duration IS NULL OR rate_duration >= 0", name="ck_sensitivity_duration"
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("instrument_id", "effective_from", name="uq_sensitivity_effective"),
    )
    op.create_index(
        "ix_sensitivity_cutoff",
        "instrument_risk_sensitivities",
        ["instrument_id", sa.text("effective_from DESC")],
    )
    op.create_table(
        "scenario_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("canonical_input_hash", sa.String(64), nullable=False),
        sa.Column("calculation_version", sa.String(64), nullable=False),
        sa.Column("baseline_value", sa.Numeric(28, 4), nullable=False),
        sa.Column("projected_value", sa.Numeric(28, 4), nullable=False),
        sa.Column("pnl_impact", sa.Numeric(28, 4), nullable=False),
        sa.Column("portfolio_return_impact", sa.Numeric(28, 12), nullable=False),
        sa.Column("benchmark_scenario_return", sa.Numeric(28, 12), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(canonical_input_hash) = 64", name="ck_scenario_run_hash"),
        sa.CheckConstraint(
            "baseline_value > 0 AND projected_value > 0", name="ck_scenario_run_values"
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenario_definitions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["policy_id"], ["risk_policies.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "scenario_id", "as_of", "canonical_input_hash", name="uq_scenario_run_input"
        ),
    )
    op.create_table(
        "scenario_position_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("baseline_market_value", sa.Numeric(28, 4), nullable=False),
        sa.Column("projected_market_value", sa.Numeric(28, 4), nullable=False),
        sa.Column("return_impact", sa.Numeric(28, 12), nullable=False),
        sa.Column("pnl_impact", sa.Numeric(28, 4), nullable=False),
        sa.Column("contribution_evidence", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint(
            "baseline_market_value >= 0 AND projected_market_value >= 0",
            name="ck_scenario_position_values",
        ),
        sa.ForeignKeyConstraint(["scenario_run_id"], ["scenario_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("scenario_run_id", "instrument_id", name="uq_scenario_position_result"),
    )
    op.execute("""
        CREATE FUNCTION protect_scenario_evidence() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'scenario evidence is immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER scenario_runs_immutable BEFORE UPDATE OR DELETE ON scenario_runs
        FOR EACH ROW EXECUTE FUNCTION protect_scenario_evidence();
        CREATE TRIGGER scenario_position_results_immutable
        BEFORE UPDATE OR DELETE ON scenario_position_results
        FOR EACH ROW EXECUTE FUNCTION protect_scenario_evidence();
        CREATE TRIGGER scenario_definitions_immutable
        BEFORE UPDATE OR DELETE ON scenario_definitions
        FOR EACH ROW EXECUTE FUNCTION protect_scenario_evidence();
        CREATE TRIGGER scenario_shocks_immutable
        BEFORE UPDATE OR DELETE ON scenario_shocks
        FOR EACH ROW EXECUTE FUNCTION protect_scenario_evidence();
        CREATE TRIGGER instrument_risk_sensitivities_immutable
        BEFORE UPDATE OR DELETE ON instrument_risk_sensitivities
        FOR EACH ROW EXECUTE FUNCTION protect_scenario_evidence();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS instrument_risk_sensitivities_immutable "
        "ON instrument_risk_sensitivities"
    )
    op.execute("DROP TRIGGER IF EXISTS scenario_shocks_immutable ON scenario_shocks")
    op.execute("DROP TRIGGER IF EXISTS scenario_definitions_immutable ON scenario_definitions")
    op.execute(
        "DROP TRIGGER IF EXISTS scenario_position_results_immutable ON scenario_position_results"
    )
    op.execute("DROP TRIGGER IF EXISTS scenario_runs_immutable ON scenario_runs")
    op.execute("DROP FUNCTION IF EXISTS protect_scenario_evidence")
    op.drop_table("scenario_position_results")
    op.drop_table("scenario_runs")
    op.drop_index("ix_sensitivity_cutoff", table_name="instrument_risk_sensitivities")
    op.drop_table("instrument_risk_sensitivities")
    op.drop_table("scenario_shocks")
    op.drop_table("scenario_definitions")
