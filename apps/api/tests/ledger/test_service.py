from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger.commands import CreateTransaction
from app.ledger.errors import OpeningBalanceError, ReversalError
from app.ledger.service import CreationStatus, TransactionService
from app.models import (
    ImportBatch,
    ImportConflict,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from tests.conftest import ACCOUNT_ID, BATCH_ID, FUND_ID, INSTRUMENT_ID

NOW = datetime(2026, 1, 10, tzinfo=UTC)


def command(
    transaction_type: TransactionType = TransactionType.BUY,
    external_id: str = "TX-001",
) -> CreateTransaction:
    return CreateTransaction(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        transaction_type=transaction_type,
        instrument_id=INSTRUMENT_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("200"),
        effective_at=NOW,
        recorded_at=NOW,
        source="hawkfund_csv",
        external_id=external_id,
        import_batch_id=BATCH_ID,
    )


def test_valid_transaction_is_persisted(session: Session) -> None:
    result = TransactionService(session).create(command())
    session.commit()

    assert result.status is CreationStatus.CREATED
    assert session.scalar(select(func.count()).select_from(Transaction)) == 1
    assert result.transaction.quantity == Decimal("100")


def test_identical_import_is_idempotent(session: Session) -> None:
    service = TransactionService(session)
    first = service.create(command())
    second = service.create(command())
    session.commit()

    assert first.transaction.id == second.transaction.id
    assert second.status is CreationStatus.DUPLICATE
    assert session.scalar(select(func.count()).select_from(Transaction)) == 1


def test_import_envelope_changes_do_not_change_economic_identity(session: Session) -> None:
    service = TransactionService(session)
    first = service.create(command())
    retried = replace(
        command(),
        recorded_at=datetime(2026, 1, 11, tzinfo=UTC),
        description="retried from a later batch envelope",
    )
    second = service.create(retried)

    assert second.status is CreationStatus.DUPLICATE
    assert second.transaction.id == first.transaction.id


def test_changed_duplicate_records_conflict_without_mutating_original(session: Session) -> None:
    service = TransactionService(session)
    original = service.create(command()).transaction
    original_hash = original.normalized_payload_hash
    result = service.create(replace(command(), quantity=Decimal("200")))
    session.commit()

    assert result.status is CreationStatus.CONFLICT
    assert result.transaction.id == original.id
    assert result.transaction.quantity == Decimal("100")
    assert result.transaction.normalized_payload_hash == original_hash
    assert result.conflict is not None
    assert result.conflict.incoming_payload_hash != original_hash
    assert session.scalar(select(func.count()).select_from(Transaction)) == 1
    assert session.scalar(select(func.count()).select_from(ImportConflict)) == 1
    batch = session.get_one(ImportBatch, BATCH_ID)
    assert batch.conflict_count == 1

    repeated = service.create(replace(command(), quantity=Decimal("200")))
    assert repeated.conflict is not None
    assert repeated.conflict.id == result.conflict.id
    assert session.scalar(select(func.count()).select_from(ImportConflict)) == 1
    assert batch.conflict_count == 1


def test_opening_position_keeps_unknown_cost_and_must_be_first(session: Session) -> None:
    service = TransactionService(session)
    opening = replace(
        command(external_id="OPEN-AAPL"),
        transaction_type=TransactionType.OPENING_POSITION,
        unit_price=None,
    )
    result = service.create(opening)
    assert result.transaction.unit_price is None

    second_opening = replace(opening, external_id="OPEN-AAPL-2")
    with pytest.raises(OpeningBalanceError, match="first posted activity"):
        service.create(second_opening)


def test_reversal_preserves_original_economics(session: Session) -> None:
    service = TransactionService(session)
    original = service.create(command()).transaction
    original_economics = (
        original.transaction_type,
        original.instrument_id,
        original.quantity,
        original.unit_price,
        original.effective_at.replace(tzinfo=None),
        original.external_id,
    )
    reversal = CreateTransaction(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        transaction_type=TransactionType.REVERSAL,
        effective_at=datetime(2026, 1, 12, tzinfo=UTC),
        recorded_at=datetime(2026, 1, 12, tzinfo=UTC),
        source="hawkfund_csv",
        external_id="REV-TX-001",
        import_batch_id=BATCH_ID,
        reverses_transaction_id=original.id,
        correction_command_id=uuid4(),
    )
    reversed_result = service.create(reversal)
    session.commit()

    session.refresh(original)
    assert reversed_result.transaction.reverses_transaction_id == original.id
    assert original.status is TransactionStatus.REVERSED
    assert original_economics == (
        original.transaction_type,
        original.instrument_id,
        original.quantity,
        original.unit_price,
        original.effective_at.replace(tzinfo=None),
        original.external_id,
    )

    with pytest.raises(ReversalError, match="already been reversed"):
        service.create(replace(reversal, external_id="REV-TX-001-AGAIN"))
