from datetime import date, datetime
from decimal import Decimal
from enum import Enum
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


class TransactionType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
    DIVIDEND = "DIVIDEND"
    FEE = "FEE"
    OPENING_CASH = "OPENING_CASH"
    OPENING_POSITION = "OPENING_POSITION"
    REVERSAL = "REVERSAL"


class TransactionStatus(str, Enum):
    POSTED = "POSTED"
    REVERSED = "REVERSED"


class ImportBatchStatus(str, Enum):
    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"


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
