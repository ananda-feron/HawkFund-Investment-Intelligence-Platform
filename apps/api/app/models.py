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

from app.db import Base
from app.ledger.types import (
    ImportBatchStatus,
    ImportRecordStatus,
    TransactionStatus,
    TransactionType,
)
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
