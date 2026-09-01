from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger.types import TransactionType
from app.models import AuditEvent, ReconciliationItem, Transaction
from app.snapshots.errors import ReconciliationError
from app.snapshots.reconciliation import ReconciliationService
from app.snapshots.service import SnapshotService
from app.snapshots.types import ReconciliationKind, ReconciliationStatus
from tests.conftest import ACCOUNT_ID, FUND_ID, INSTRUMENT_ID
from tests.snapshots.factories import instant, post

CUTOFF = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
NOW = datetime(2026, 3, 5, tzinfo=UTC)


def snapshot_with_state(session: Session):
    post(
        session,
        1,
        TransactionType.OPENING_CASH,
        effective_at=instant(1, 1),
        amount=Decimal("1000"),
    )
    post(
        session,
        2,
        TransactionType.BUY,
        effective_at=instant(1, 10),
        instrument=True,
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
    )
    return (
        SnapshotService(session, clock=lambda: NOW)
        .create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)
        .snapshot
    )


def reconciliation(session: Session) -> ReconciliationService:
    return ReconciliationService(session, clock=lambda: NOW)


def test_matching_cash_and_position_evidence(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    service = reconciliation(session)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.CASH,
        reported_value=Decimal("800"),
        source="custodian",
        external_id="CASH-0131",
    )
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.POSITION,
        instrument_id=INSTRUMENT_ID,
        reported_value=Decimal("10"),
        source="custodian",
        external_id="AAPL-0131",
    )

    result = service.reconcile(snapshot_id=snapshot.id)

    assert result.run.status is ReconciliationStatus.MATCHED
    assert len(result.items) == 2
    assert all(item.difference == 0 for item in result.items)
    assert all(item.status is ReconciliationStatus.MATCHED for item in result.items)


def test_discrepancy_is_recorded_without_mutating_ledger(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    transaction_count = session.scalar(select(func.count()).select_from(Transaction))
    service = reconciliation(session)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.CASH,
        reported_value=Decimal("780"),
        source="custodian",
        external_id="CASH-BREACH",
        evidence={"statement": "statement-0131.csv"},
    )

    result = service.reconcile(snapshot_id=snapshot.id, tolerance=Decimal("0.01"))

    assert result.run.status is ReconciliationStatus.BREACH
    assert result.items[0].expected_value == Decimal("800")
    assert result.items[0].reported_value == Decimal("780")
    assert result.items[0].difference == Decimal("-20")
    assert session.scalar(select(func.count()).select_from(Transaction)) == transaction_count


def test_tolerance_controls_discrepancy_status(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    service = reconciliation(session)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.CASH,
        reported_value=Decimal("800.005"),
        source="custodian",
        external_id="CASH-TOLERANCE",
    )

    result = service.reconcile(snapshot_id=snapshot.id, tolerance=Decimal("0.01"))
    assert result.run.status is ReconciliationStatus.MATCHED


def test_no_evidence_produces_unavailable_run(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    result = reconciliation(session).reconcile(snapshot_id=snapshot.id)

    assert result.run.status is ReconciliationStatus.UNAVAILABLE
    assert result.items == ()


def test_reconciliation_is_idempotent_and_audited(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    service = reconciliation(session)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.CASH,
        reported_value=Decimal("800"),
        source="custodian",
        external_id="CASH-IDEMPOTENT",
    )
    first = service.reconcile(snapshot_id=snapshot.id)
    second = service.reconcile(snapshot_id=snapshot.id)

    assert second.reused is True
    assert second.run.id == first.run.id
    assert session.scalar(select(func.count()).select_from(ReconciliationItem)) == 1
    event = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == first.run.id))
    assert event is not None
    assert event.action == "PORTFOLIO_RECONCILIATION_COMPLETED"


def test_late_evidence_creates_a_new_reconciliation_run(session: Session) -> None:
    snapshot = snapshot_with_state(session)
    service = reconciliation(session)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.CASH,
        reported_value=Decimal("800"),
        source="custodian",
        external_id="CASH-FIRST",
    )
    first = service.reconcile(snapshot_id=snapshot.id)
    service.record_observation(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=CUTOFF,
        kind=ReconciliationKind.POSITION,
        instrument_id=INSTRUMENT_ID,
        reported_value=Decimal("9"),
        source="custodian",
        external_id="POSITION-LATE",
    )
    second = service.reconcile(snapshot_id=snapshot.id)

    assert second.reused is False
    assert second.run.id != first.run.id
    assert second.run.evidence_hash != first.run.evidence_hash
    assert second.run.status is ReconciliationStatus.BREACH
    assert len(second.items) == 2


def test_observation_identity_conflict_is_rejected(session: Session) -> None:
    service = reconciliation(session)
    arguments = {
        "fund_id": FUND_ID,
        "account_id": ACCOUNT_ID,
        "as_of": CUTOFF,
        "kind": ReconciliationKind.CASH,
        "reported_value": Decimal("800"),
        "source": "custodian",
        "external_id": "CASH-CONFLICT",
    }
    original = service.record_observation(**arguments)
    duplicate = service.record_observation(**arguments)
    assert duplicate.id == original.id

    with pytest.raises(ReconciliationError, match="conflicts"):
        service.record_observation(**{**arguments, "reported_value": Decimal("801")})
