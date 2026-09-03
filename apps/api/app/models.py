from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.types import AIMessageRole, ConversationStatus, ToolExecutionStatus
from app.db import Base
from app.governance.types import (
    ProposalAction,
    ProposalStatus,
    ReviewRecommendation,
    WorkflowAction,
)
from app.ledger.types import (
    ImportBatchStatus,
    ImportRecordStatus,
    TransactionStatus,
    TransactionType,
)
from app.market_data.types import (
    IdentifierScheme,
    MarketDataBatchStatus,
    PriceType,
)
from app.risk.policy import PolicyEvaluationStatus, PolicyOperator, PolicyRuleSeverity
from app.scenarios.types import ScenarioKind, ShockTargetType, ShockUnit
from app.snapshots.types import (
    CostBasisPersistenceStatus,
    ReconciliationKind,
    ReconciliationStatus,
    SnapshotStatus,
)


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    base_currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(160))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(80))


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    fund_id: Mapped[UUID] = mapped_column(
        ForeignKey("funds.id", ondelete="CASCADE"), primary_key=True
    )


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24))
    name: Mapped[str] = mapped_column(String(200))
    asset_type: Mapped[str] = mapped_column(String(32))
    exchange: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("symbol", "exchange"),)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("fund_id", "code", name="uq_accounts_fund_code"),
        UniqueConstraint("id", "fund_id", name="uq_accounts_id_fund"),
        CheckConstraint("currency = 'USD'", name="ck_accounts_phase1_usd"),
    )


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str | None] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[ImportBatchStatus] = mapped_column(
        SqlEnum(ImportBatchStatus, native_enum=False, length=32),
        default=ImportBatchStatus.RECEIVED,
    )
    initiated_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_count: Mapped[int] = mapped_column(default=0)
    posted_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    rejected_count: Mapped[int] = mapped_column(default=0)
    conflict_count: Mapped[int] = mapped_column(default=0)
    failure_summary: Mapped[str | None] = mapped_column(String(1000))

    __table_args__ = (
        UniqueConstraint("fund_id", "source", "content_sha256", name="uq_import_batches_content"),
        CheckConstraint("length(content_sha256) = 64", name="ck_import_batches_sha256"),
        CheckConstraint(
            "total_count >= 0 AND posted_count >= 0 AND duplicate_count >= 0 "
            "AND rejected_count >= 0 AND conflict_count >= 0",
            name="ck_import_batches_nonnegative_counts",
        ),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID] = mapped_column()
    instrument_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT")
    )
    transaction_type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType, native_enum=False, length=32)
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    fees: Mapped[Decimal] = mapped_column(Numeric(28, 4), default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trade_date: Mapped[date | None] = mapped_column(Date)
    settlement_date: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(160))
    normalized_payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[TransactionStatus] = mapped_column(
        SqlEnum(TransactionStatus, native_enum=False, length=16),
        default=TransactionStatus.POSTED,
    )
    import_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    reverses_transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT")
    )
    correction_command_id: Mapped[UUID | None] = mapped_column()
    description: Mapped[str | None] = mapped_column(String(500))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "fund_id"],
            ["accounts.id", "accounts.fund_id"],
            ondelete="RESTRICT",
            name="fk_transactions_account_fund",
        ),
        UniqueConstraint(
            "fund_id", "source", "external_id", name="uq_transactions_source_identity"
        ),
        UniqueConstraint("reverses_transaction_id", name="uq_transactions_one_reversal"),
        CheckConstraint("currency = 'USD'", name="ck_transactions_phase1_usd"),
        CheckConstraint("length(normalized_payload_hash) = 64", name="ck_transactions_hash"),
        CheckConstraint("fees >= 0", name="ck_transactions_nonnegative_fees"),
        CheckConstraint("quantity IS NULL OR quantity > 0", name="ck_transactions_quantity"),
        CheckConstraint("unit_price IS NULL OR unit_price > 0", name="ck_transactions_price"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_transactions_amount"),
        CheckConstraint(
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
        CheckConstraint(
            "(transaction_type = 'REVERSAL') = (reverses_transaction_id IS NOT NULL)",
            name="ck_transactions_reversal_reference",
        ),
    )


class ImportConflict(Base):
    __tablename__ = "import_conflicts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    existing_transaction_id: Mapped[UUID] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT")
    )
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(160))
    existing_payload_hash: Mapped[str] = mapped_column(String(64))
    incoming_payload_hash: Mapped[str] = mapped_column(String(64))
    incoming_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("length(existing_payload_hash) = 64", name="ck_conflicts_existing_hash"),
        CheckConstraint("length(incoming_payload_hash) = 64", name="ck_conflicts_incoming_hash"),
        UniqueConstraint(
            "import_batch_id",
            "source",
            "external_id",
            "incoming_payload_hash",
            name="uq_import_conflicts_evidence",
        ),
    )


class ImportRecord(Base):
    __tablename__ = "import_records"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE")
    )
    row_number: Mapped[int] = mapped_column()
    source_locator: Mapped[str] = mapped_column(String(255))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    normalized_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    raw_payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ImportRecordStatus] = mapped_column(
        SqlEnum(ImportRecordStatus, native_enum=False, length=16)
    )
    transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT")
    )
    import_conflict_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_conflicts.id", ondelete="RESTRICT")
    )
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("import_batch_id", "row_number", name="uq_import_records_batch_row"),
        CheckConstraint("row_number > 0", name="ck_import_records_positive_row"),
        CheckConstraint("length(raw_payload_hash) = 64", name="ck_import_records_hash"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSON)


class PortfolioSnapshot(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column()
    status: Mapped[SnapshotStatus] = mapped_column(
        SqlEnum(SnapshotStatus, native_enum=False, length=16)
    )
    calculation_version: Mapped[str] = mapped_column(String(64))
    canonical_input_hash: Mapped[str] = mapped_column(String(64))
    canonical_state: Mapped[dict[str, Any]] = mapped_column(JSON)
    applied_transaction_count: Mapped[int] = mapped_column()
    last_applied_transaction_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="RESTRICT")
    )
    supersedes_snapshot_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("revision > 0", name="ck_snapshots_positive_revision"),
        CheckConstraint("applied_transaction_count >= 0", name="ck_snapshots_nonnegative_count"),
        CheckConstraint("length(canonical_input_hash) = 64", name="ck_snapshots_hash"),
    )


class SnapshotCash(Base):
    __tablename__ = "snapshot_cash"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE")
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 4))

    __table_args__ = (
        UniqueConstraint("snapshot_id", "account_id", "currency", name="uq_snapshot_cash"),
        CheckConstraint("currency = 'USD'", name="ck_snapshot_cash_usd"),
    )


class SnapshotPosition(Base):
    __tablename__ = "snapshot_positions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="CASCADE")
    )
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    total_cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(28, 4))
    average_cost: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    cost_basis_status: Mapped[CostBasisPersistenceStatus] = mapped_column(
        SqlEnum(CostBasisPersistenceStatus, native_enum=False, length=16)
    )
    source_transaction_ids: Mapped[list[str]] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("snapshot_id", "account_id", "instrument_id", name="uq_snapshot_position"),
        CheckConstraint("quantity > 0", name="ck_snapshot_position_quantity"),
        CheckConstraint(
            "(cost_basis_status = 'KNOWN' AND total_cost_basis IS NOT NULL "
            "AND average_cost IS NOT NULL) OR "
            "(cost_basis_status = 'UNKNOWN' AND total_cost_basis IS NULL "
            "AND average_cost IS NULL)",
            name="ck_snapshot_position_basis_status",
        ),
    )


class ReconciliationObservation(Base):
    __tablename__ = "reconciliation_observations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[ReconciliationKind] = mapped_column(
        SqlEnum(ReconciliationKind, native_enum=False, length=16)
    )
    instrument_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT")
    )
    reported_value: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    currency: Mapped[str] = mapped_column(String(3))
    source: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(160))
    import_batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="RESTRICT")
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "fund_id", "source", "external_id", name="uq_reconciliation_observation_source"
        ),
        CheckConstraint("currency = 'USD'", name="ck_reconciliation_observation_usd"),
        CheckConstraint(
            "(kind = 'CASH' AND instrument_id IS NULL) OR "
            "(kind = 'POSITION' AND instrument_id IS NOT NULL AND reported_value >= 0)",
            name="ck_reconciliation_observation_kind",
        ),
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("portfolio_snapshots.id", ondelete="RESTRICT")
    )
    tolerance: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    evidence_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ReconciliationStatus] = mapped_column(
        SqlEnum(ReconciliationStatus, native_enum=False, length=16)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("snapshot_id", "tolerance", "evidence_hash", name="uq_reconciliation_run"),
        CheckConstraint("tolerance >= 0", name="ck_reconciliation_tolerance"),
        CheckConstraint("length(evidence_hash) = 64", name="ck_reconciliation_evidence_hash"),
    )


class ReconciliationItem(Base):
    __tablename__ = "reconciliation_items"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    reconciliation_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_runs.id", ondelete="CASCADE")
    )
    observation_id: Mapped[UUID] = mapped_column(
        ForeignKey("reconciliation_observations.id", ondelete="RESTRICT")
    )
    expected_value: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    reported_value: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    difference: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    tolerance: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    status: Mapped[ReconciliationStatus] = mapped_column(
        SqlEnum(ReconciliationStatus, native_enum=False, length=16)
    )

    __table_args__ = (
        UniqueConstraint("reconciliation_run_id", "observation_id", name="uq_reconciliation_item"),
    )


class SecurityIdentifier(Base):
    __tablename__ = "security_identifiers"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    scheme: Mapped[IdentifierScheme] = mapped_column(
        SqlEnum(IdentifierScheme, native_enum=False, length=16)
    )
    value: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64), default="")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("scheme", "value", "provider", name="uq_security_identifier"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_identifier_range",
        ),
    )


class MarketDataBatch(Base):
    __tablename__ = "market_data_batches"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(64))
    dataset: Mapped[str] = mapped_column(String(64))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[MarketDataBatchStatus] = mapped_column(
        SqlEnum(MarketDataBatchStatus, native_enum=False, length=32)
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    inserted_count: Mapped[int] = mapped_column(default=0)
    duplicate_count: Mapped[int] = mapped_column(default=0)
    conflict_count: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint(
            "provider", "dataset", "request_hash", name="uq_market_data_batch_request"
        ),
        CheckConstraint("length(request_hash) = 64", name="ck_market_data_batch_hash"),
        CheckConstraint(
            "inserted_count >= 0 AND duplicate_count >= 0 AND conflict_count >= 0",
            name="ck_market_data_batch_counts",
        ),
    )


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT")
    )
    provider: Mapped[str] = mapped_column(String(64))
    price_type: Mapped[PriceType] = mapped_column(SqlEnum(PriceType, native_enum=False, length=24))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    price: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    currency: Mapped[str] = mapped_column(String(3))
    source_identifier: Mapped[str] = mapped_column(String(64))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "instrument_id",
            "provider",
            "price_type",
            "observed_at",
            name="uq_market_price_observation",
        ),
        CheckConstraint("price > 0", name="ck_market_price_positive"),
        CheckConstraint("currency = 'USD'", name="ck_market_price_usd"),
    )


class MarketPriceConflict(Base):
    __tablename__ = "market_price_conflicts"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_data_batches.id", ondelete="RESTRICT")
    )
    existing_price_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_prices.id", ondelete="RESTRICT")
    )
    incoming_price: Mapped[Decimal] = mapped_column(Numeric(28, 8))
    incoming_currency: Mapped[str] = mapped_column(String(3))
    incoming_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "batch_id", "existing_price_id", "incoming_price", name="uq_market_price_conflict"
        ),
        CheckConstraint("incoming_price > 0", name="ck_market_price_conflict_positive"),
        CheckConstraint("incoming_currency = 'USD'", name="ck_market_price_conflict_usd"),
    )


class InstrumentClassificationRecord(Base):
    __tablename__ = "instrument_classifications"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    sector: Mapped[str] = mapped_column(String(80))
    asset_class: Mapped[str] = mapped_column(String(80))
    geography: Mapped[str] = mapped_column(String(80))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(64))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("instrument_id", "effective_from", name="uq_classification_effective"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_classification_range"
        ),
    )


class RiskPolicy(Base):
    __tablename__ = "risk_policies"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[int] = mapped_column()
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("fund_id", "name", "version", name="uq_risk_policy_version"),
        CheckConstraint("version > 0", name="ck_risk_policy_version"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_risk_policy_range"
        ),
    )


class RiskPolicyRule(Base):
    __tablename__ = "risk_policy_rules"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("risk_policies.id", ondelete="RESTRICT"))
    metric_key: Mapped[str] = mapped_column(String(160))
    operator: Mapped[PolicyOperator] = mapped_column(
        SqlEnum(PolicyOperator, native_enum=False, length=8)
    )
    threshold: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    unit: Mapped[str] = mapped_column(String(32))
    explanation_template: Mapped[str] = mapped_column(String(500))
    severity: Mapped[PolicyRuleSeverity] = mapped_column(
        SqlEnum(PolicyRuleSeverity, native_enum=False, length=16),
        default=PolicyRuleSeverity.BLOCKING,
    )

    __table_args__ = (
        UniqueConstraint("policy_id", "metric_key", name="uq_risk_policy_rule_metric"),
        CheckConstraint("threshold >= 0", name="ck_risk_policy_rule_threshold"),
    )


class RiskEvaluation(Base):
    __tablename__ = "risk_evaluations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("risk_policies.id", ondelete="RESTRICT"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    input_hash: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("policy_id", "as_of", "input_hash", name="uq_risk_evaluation_input"),
        CheckConstraint("length(input_hash) = 64", name="ck_risk_evaluation_hash"),
    )


class RiskEvaluationItem(Base):
    __tablename__ = "risk_evaluation_items"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("risk_evaluations.id", ondelete="CASCADE")
    )
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("risk_policy_rules.id", ondelete="RESTRICT"))
    status: Mapped[PolicyEvaluationStatus] = mapped_column(
        SqlEnum(PolicyEvaluationStatus, native_enum=False, length=16)
    )
    observed_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    threshold: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    breach_amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    unit: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(String(1000))

    __table_args__ = (
        UniqueConstraint("evaluation_id", "rule_id", name="uq_risk_evaluation_rule"),
        CheckConstraint("threshold >= 0", name="ck_risk_evaluation_threshold"),
        CheckConstraint(
            "breach_amount IS NULL OR breach_amount >= 0", name="ck_risk_evaluation_breach"
        ),
    )


class ScenarioDefinitionRecord(Base):
    __tablename__ = "scenario_definitions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(160))
    version: Mapped[int] = mapped_column()
    kind: Mapped[ScenarioKind] = mapped_column(SqlEnum(ScenarioKind, native_enum=False, length=16))
    description: Mapped[str] = mapped_column(String(1000))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))

    __table_args__ = (
        UniqueConstraint("fund_id", "name", "version", name="uq_scenario_version"),
        CheckConstraint("version > 0", name="ck_scenario_version"),
    )


class ScenarioShockRecord(Base):
    __tablename__ = "scenario_shocks"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_definitions.id", ondelete="RESTRICT")
    )
    target_type: Mapped[ShockTargetType] = mapped_column(
        SqlEnum(ShockTargetType, native_enum=False, length=16)
    )
    target: Mapped[str] = mapped_column(String(160))
    magnitude: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    unit: Mapped[ShockUnit] = mapped_column(SqlEnum(ShockUnit, native_enum=False, length=24))
    sequence: Mapped[int] = mapped_column()

    __table_args__ = (
        UniqueConstraint("scenario_id", "sequence", name="uq_scenario_shock_sequence"),
        CheckConstraint("sequence > 0", name="ck_scenario_shock_sequence"),
    )


class InstrumentRiskSensitivity(Base):
    __tablename__ = "instrument_risk_sensitivities"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rate_duration: Mapped[Decimal | None] = mapped_column(Numeric(28, 12))
    factor_loadings: Mapped[dict[str, str]] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(64))
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("instrument_id", "effective_from", name="uq_sensitivity_effective"),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="ck_sensitivity_range"
        ),
        CheckConstraint(
            "rate_duration IS NULL OR rate_duration >= 0", name="ck_sensitivity_duration"
        ),
    )


class ScenarioRun(Base):
    __tablename__ = "scenario_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_definitions.id", ondelete="RESTRICT")
    )
    policy_id: Mapped[UUID] = mapped_column(ForeignKey("risk_policies.id", ondelete="RESTRICT"))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    canonical_input_hash: Mapped[str] = mapped_column(String(64))
    calculation_version: Mapped[str] = mapped_column(String(64))
    baseline_value: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    projected_value: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    pnl_impact: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    portfolio_return_impact: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    benchmark_scenario_return: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "as_of", "canonical_input_hash", name="uq_scenario_run_input"
        ),
        CheckConstraint("length(canonical_input_hash) = 64", name="ck_scenario_run_hash"),
        CheckConstraint(
            "baseline_value > 0 AND projected_value > 0", name="ck_scenario_run_values"
        ),
    )


class ScenarioPositionResultRecord(Base):
    __tablename__ = "scenario_position_results"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    scenario_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("scenario_runs.id", ondelete="CASCADE")
    )
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    baseline_market_value: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    projected_market_value: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    return_impact: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    pnl_impact: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    contribution_evidence: Mapped[list[dict[str, str]]] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("scenario_run_id", "instrument_id", name="uq_scenario_position_result"),
        CheckConstraint(
            "baseline_market_value >= 0 AND projected_market_value >= 0",
            name="ck_scenario_position_values",
        ),
    )


class InvestmentProposal(Base):
    __tablename__ = "investment_proposals"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[ProposalStatus] = mapped_column(
        SqlEnum(ProposalStatus, native_enum=False, length=24)
    )
    current_version: Mapped[int] = mapped_column()
    row_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("current_version > 0", name="ck_proposal_current_version"),
        CheckConstraint("row_version > 0", name="ck_proposal_row_version"),
    )


class ProposalVersion(Base):
    __tablename__ = "proposal_versions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("investment_proposals.id", ondelete="RESTRICT")
    )
    version: Mapped[int] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    thesis: Mapped[str] = mapped_column(String(5000))
    portfolio_input_hash: Mapped[str] = mapped_column(String(64))
    portfolio_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    supersedes_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint("proposal_id", "version", name="uq_proposal_version"),
        CheckConstraint("version > 0", name="ck_proposal_version"),
        CheckConstraint("length(portfolio_input_hash) = 64", name="ck_proposal_portfolio_hash"),
        CheckConstraint("length(content_hash) = 64", name="ck_proposal_content_hash"),
    )


class ProposalLine(Base):
    __tablename__ = "proposal_lines"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    proposal_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="RESTRICT")
    )
    instrument_id: Mapped[UUID] = mapped_column(ForeignKey("instruments.id", ondelete="RESTRICT"))
    action: Mapped[ProposalAction] = mapped_column(
        SqlEnum(ProposalAction, native_enum=False, length=8)
    )
    current_weight: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    proposed_weight: Mapped[Decimal] = mapped_column(Numeric(28, 12))
    estimated_notional: Mapped[Decimal] = mapped_column(Numeric(28, 4))
    rationale: Mapped[str] = mapped_column(String(1000))

    __table_args__ = (
        UniqueConstraint(
            "proposal_version_id", "instrument_id", name="uq_proposal_line_instrument"
        ),
        CheckConstraint(
            "current_weight >= 0 AND current_weight <= 1", name="ck_proposal_line_current_weight"
        ),
        CheckConstraint(
            "proposed_weight >= 0 AND proposed_weight <= 1", name="ck_proposal_line_proposed_weight"
        ),
        CheckConstraint("estimated_notional >= 0", name="ck_proposal_line_notional"),
    )


class ProposalAnalysis(Base):
    __tablename__ = "proposal_analyses"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    proposal_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="RESTRICT")
    )
    risk_evaluation_id: Mapped[UUID] = mapped_column(
        ForeignKey("risk_evaluations.id", ondelete="RESTRICT")
    )
    scenario_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("scenario_runs.id", ondelete="RESTRICT")
    )
    recorded_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    evidence_hash: Mapped[str] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint(
            "proposal_version_id", "evidence_hash", name="uq_proposal_analysis_evidence"
        ),
        CheckConstraint("length(evidence_hash) = 64", name="ck_proposal_analysis_hash"),
    )


class ProposalReview(Base):
    __tablename__ = "proposal_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("investment_proposals.id", ondelete="RESTRICT")
    )
    proposal_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="RESTRICT")
    )
    reviewer_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    reviewer_role: Mapped[str] = mapped_column(String(32))
    recommendation: Mapped[ReviewRecommendation] = mapped_column(
        SqlEnum(ReviewRecommendation, native_enum=False, length=16)
    )
    comment: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProposalTransition(Base):
    __tablename__ = "proposal_transitions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("investment_proposals.id", ondelete="RESTRICT")
    )
    proposal_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("proposal_versions.id", ondelete="RESTRICT")
    )
    action: Mapped[WorkflowAction] = mapped_column(
        SqlEnum(WorkflowAction, native_enum=False, length=24)
    )
    from_status: Mapped[ProposalStatus | None] = mapped_column(
        SqlEnum(ProposalStatus, native_enum=False, length=24)
    )
    to_status: Mapped[ProposalStatus] = mapped_column(
        SqlEnum(ProposalStatus, native_enum=False, length=24)
    )
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    actor_role: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(2000))
    decision_provenance: Mapped[dict[str, Any]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resulting_row_version: Mapped[int] = mapped_column()

    __table_args__ = (
        CheckConstraint("resulting_row_version > 0", name="ck_proposal_transition_version"),
    )


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    fund_id: Mapped[UUID] = mapped_column(ForeignKey("funds.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    status: Mapped[ConversationStatus] = mapped_column(
        SqlEnum(ConversationStatus, native_enum=False, length=16)
    )
    model: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="RESTRICT")
    )
    role: Mapped[AIMessageRole] = mapped_column(
        SqlEnum(AIMessageRole, native_enum=False, length=16)
    )
    content: Mapped[str] = mapped_column(String(20000))
    content_hash: Mapped[str] = mapped_column(String(64))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    provider_response_id: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("length(content_hash) = 64", name="ck_ai_message_hash"),)


class AIToolCall(Base):
    __tablename__ = "ai_tool_calls"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="RESTRICT")
    )
    provider_call_id: Mapped[str] = mapped_column(String(160))
    tool_name: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[ToolExecutionStatus] = mapped_column(
        SqlEnum(ToolExecutionStatus, native_enum=False, length=16)
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_hash: Mapped[str | None] = mapped_column(String(64))
    sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(2000))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("conversation_id", "provider_call_id", name="uq_ai_tool_call"),
        CheckConstraint(
            "result_hash IS NULL OR length(result_hash) = 64", name="ck_ai_tool_result_hash"
        ),
    )
