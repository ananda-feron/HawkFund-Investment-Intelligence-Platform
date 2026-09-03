"""Add governed AI conversations, messages, tool calls, and provenance."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_ai_intelligence"
down_revision: str | None = "0008_investment_governance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("fund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "status IN ('ACTIVE','COMPLETED','REFUSED','FAILED')",
            name="ck_ai_conversation_status",
        ),
        sa.ForeignKeyConstraint(["fund_id"], ["funds.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "ai_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.String(20000), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("provider_response_id", sa.String(160)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('USER','ASSISTANT','REFUSAL')", name="ck_ai_message_role"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_ai_message_hash"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="RESTRICT"),
    )
    op.create_table(
        "ai_tool_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_call_id", sa.String(160), nullable=False),
        sa.Column("tool_name", sa.String(80), nullable=False),
        sa.Column("arguments", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("result_hash", sa.String(64)),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.String(2000)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED','UNAVAILABLE','DENIED','INVALID')",
            name="ck_ai_tool_call_status",
        ),
        sa.CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64",
            name="ck_ai_tool_result_hash",
        ),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("conversation_id", "provider_call_id", name="uq_ai_tool_call"),
    )
    op.create_index(
        "ix_ai_conversation_history",
        "ai_conversations",
        ["fund_id", "actor_user_id", "created_at"],
    )
    op.create_index("ix_ai_message_history", "ai_messages", ["conversation_id", "created_at"])
    op.create_index("ix_ai_tool_call_history", "ai_tool_calls", ["conversation_id", "occurred_at"])
    op.execute("""
        CREATE FUNCTION protect_ai_evidence() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'AI evidence is immutable'; END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_messages_immutable BEFORE UPDATE OR DELETE ON ai_messages
        FOR EACH ROW EXECUTE FUNCTION protect_ai_evidence();
        CREATE TRIGGER ai_tool_calls_immutable BEFORE UPDATE OR DELETE ON ai_tool_calls
        FOR EACH ROW EXECUTE FUNCTION protect_ai_evidence();

        CREATE FUNCTION protect_ai_conversation() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE'
                OR NEW.fund_id IS DISTINCT FROM OLD.fund_id
                OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
                OR NEW.model IS DISTINCT FROM OLD.model
                OR NEW.created_at IS DISTINCT FROM OLD.created_at
                OR OLD.status <> 'ACTIVE'
                OR NEW.status NOT IN ('COMPLETED','REFUSED','FAILED')
                OR NEW.completed_at IS NULL
            THEN RAISE EXCEPTION 'AI conversation invariant violated';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER ai_conversations_controlled_update
        BEFORE UPDATE OR DELETE ON ai_conversations
        FOR EACH ROW EXECUTE FUNCTION protect_ai_conversation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ai_conversations_controlled_update ON ai_conversations")
    op.execute("DROP FUNCTION IF EXISTS protect_ai_conversation")
    op.execute("DROP TRIGGER IF EXISTS ai_tool_calls_immutable ON ai_tool_calls")
    op.execute("DROP TRIGGER IF EXISTS ai_messages_immutable ON ai_messages")
    op.execute("DROP FUNCTION IF EXISTS protect_ai_evidence")
    op.drop_index("ix_ai_tool_call_history", table_name="ai_tool_calls")
    op.drop_index("ix_ai_message_history", table_name="ai_messages")
    op.drop_index("ix_ai_conversation_history", table_name="ai_conversations")
    op.drop_table("ai_tool_calls")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
