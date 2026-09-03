"""Add controlled investment proposals, authorization evidence, and approval history."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_investment_governance"
down_revision: str | None = "0007_scenario_stress_testing"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "risk_policy_rules",
        sa.Column("severity", sa.String(16), nullable=False, server_default="BLOCKING"),
    )
    op.create_check_constraint(
        "ck_risk_policy_rule_severity",
        "risk_policy_rules",
        "severity IN ('BLOCKING','WARNING')",
    )
    op.create_table(
        "investment_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_version > 0", name="ck_proposal_current_version"),
        sa.CheckConstraint("row_version > 0", name="ck_proposal_row_version"),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','CHANGES_REQUESTED',"
            "'APPROVED','REJECTED','WITHDRAWN')",
            name="ck_proposal_status",
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "proposal_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("thesis", sa.String(5000), nullable=False),
        sa.Column("portfolio_input_hash", sa.String(64), nullable=False),
        sa.Column("portfolio_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("supersedes_version_id", postgresql.UUID(as_uuid=True)),
        sa.CheckConstraint("version > 0", name="ck_proposal_version"),
        sa.CheckConstraint("length(portfolio_input_hash) = 64", name="ck_proposal_portfolio_hash"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_proposal_content_hash"),
        sa.ForeignKeyConstraint(["proposal_id"], ["investment_proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["supersedes_version_id"], ["proposal_versions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("proposal_id", "version", name="uq_proposal_version"),
    )
    op.create_table(
        "proposal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(8), nullable=False),
        sa.Column("current_weight", sa.Numeric(28, 12), nullable=False),
        sa.Column("proposed_weight", sa.Numeric(28, 12), nullable=False),
        sa.Column("estimated_notional", sa.Numeric(28, 4), nullable=False),
        sa.Column("rationale", sa.String(1000), nullable=False),
        sa.CheckConstraint(
            "action IN ('BUY','SELL','EXIT','HOLD')", name="ck_proposal_line_action"
        ),
        sa.CheckConstraint(
            "current_weight >= 0 AND current_weight <= 1",
            name="ck_proposal_line_current_weight",
        ),
        sa.CheckConstraint(
            "proposed_weight >= 0 AND proposed_weight <= 1",
            name="ck_proposal_line_proposed_weight",
        ),
        sa.CheckConstraint("estimated_notional >= 0", name="ck_proposal_line_notional"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["proposal_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["instrument_id"], ["instruments.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "proposal_version_id", "instrument_id", name="uq_proposal_line_instrument"
        ),
    )
    op.create_table(
        "proposal_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recorded_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.CheckConstraint("length(evidence_hash) = 64", name="ck_proposal_analysis_hash"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["proposal_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["risk_evaluation_id"], ["risk_evaluations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["scenario_run_id"], ["scenario_runs.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recorded_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "proposal_version_id", "evidence_hash", name="uq_proposal_analysis_evidence"
        ),
    )
    op.create_table(
        "proposal_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_role", sa.String(32), nullable=False),
        sa.Column("recommendation", sa.String(16), nullable=False),
        sa.Column("comment", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "reviewer_role IN ('analyst','manager','advisor')", name="ck_proposal_review_role"
        ),
        sa.CheckConstraint(
            "recommendation IN ('SUPPORT','OPPOSE','COMMENT')",
            name="ck_proposal_review_recommendation",
        ),
        sa.ForeignKeyConstraint(["proposal_id"], ["investment_proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["proposal_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["reviewer_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "proposal_transitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("from_status", sa.String(24)),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(2000)),
        sa.Column("decision_provenance", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resulting_row_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "action IN ('CREATED','REVISED','ANALYZED','SUBMITTED','REVIEW_STARTED',"
            "'REVIEW_RECORDED','CHANGES_REQUESTED','APPROVED','REJECTED','WITHDRAWN')",
            name="ck_proposal_transition_action",
        ),
        sa.CheckConstraint(
            "actor_role IN ('analyst','manager','advisor')", name="ck_proposal_transition_role"
        ),
        sa.CheckConstraint("resulting_row_version > 0", name="ck_proposal_transition_version"),
        sa.ForeignKeyConstraint(["proposal_id"], ["investment_proposals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["proposal_version_id"], ["proposal_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_proposal_transition_history",
        "proposal_transitions",
        ["proposal_id", "occurred_at"],
    )
    op.execute("""
        CREATE FUNCTION protect_governance_evidence() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'governance evidence is immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER proposal_versions_immutable BEFORE UPDATE OR DELETE ON proposal_versions
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER proposal_lines_immutable BEFORE UPDATE OR DELETE ON proposal_lines
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER proposal_analyses_immutable BEFORE UPDATE OR DELETE ON proposal_analyses
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER proposal_reviews_immutable BEFORE UPDATE OR DELETE ON proposal_reviews
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER proposal_transitions_immutable
        BEFORE UPDATE OR DELETE ON proposal_transitions
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER risk_policies_immutable BEFORE UPDATE OR DELETE ON risk_policies
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();
        CREATE TRIGGER risk_policy_rules_immutable BEFORE UPDATE OR DELETE ON risk_policy_rules
        FOR EACH ROW EXECUTE FUNCTION protect_governance_evidence();

        CREATE FUNCTION protect_proposal_identity() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                OR NEW.fund_id IS DISTINCT FROM OLD.fund_id
                OR NEW.created_by_user_id IS DISTINCT FROM OLD.created_by_user_id
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR NEW.current_version < OLD.current_version
                OR NEW.row_version <> OLD.row_version + 1
            THEN RAISE EXCEPTION 'proposal identity or version invariant violated';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER investment_proposals_controlled_update
        BEFORE UPDATE OR DELETE ON investment_proposals
        FOR EACH ROW EXECUTE FUNCTION protect_proposal_identity();
    """)


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS investment_proposals_controlled_update ON investment_proposals"
    )
    op.execute("DROP FUNCTION IF EXISTS protect_proposal_identity")
    op.execute("DROP TRIGGER IF EXISTS risk_policy_rules_immutable ON risk_policy_rules")
    op.execute("DROP TRIGGER IF EXISTS risk_policies_immutable ON risk_policies")
    for table in (
        "proposal_transitions",
        "proposal_reviews",
        "proposal_analyses",
        "proposal_lines",
        "proposal_versions",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_immutable ON {table}")
    op.execute("DROP FUNCTION IF EXISTS protect_governance_evidence")
    op.drop_index("ix_proposal_transition_history", table_name="proposal_transitions")
    op.drop_table("proposal_transitions")
    op.drop_table("proposal_reviews")
    op.drop_table("proposal_analyses")
    op.drop_table("proposal_lines")
    op.drop_table("proposal_versions")
    op.drop_table("investment_proposals")
    op.drop_constraint("ck_risk_policy_rule_severity", "risk_policy_rules", type_="check")
    op.drop_column("risk_policy_rules", "severity")
