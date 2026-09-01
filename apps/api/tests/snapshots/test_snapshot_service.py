from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ledger.types import TransactionType
from app.models import (
    AuditEvent,
    PortfolioSnapshot,
    SnapshotCash,
    SnapshotPosition,
)
from app.snapshots.service import SnapshotOutcome, SnapshotService
from app.snapshots.types import CostBasisPersistenceStatus, SnapshotStatus
from tests.conftest import ACCOUNT_ID, FUND_ID
from tests.snapshots.factories import instant, post

CUTOFF = datetime(2026, 1, 31, 23, 59, tzinfo=UTC)
NOW = datetime(2026, 3, 5, tzinfo=UTC)


def service(session: Session) -> SnapshotService:
    return SnapshotService(session, clock=lambda: NOW)


def seed_history(session: Session) -> None:
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
    post(
        session,
        3,
        TransactionType.BUY,
        effective_at=instant(2, 10),
        instrument=True,
        quantity=Decimal("5"),
        unit_price=Decimal("30"),
    )


def test_point_in_time_snapshot_persists_reconstructed_state(session: Session) -> None:
    seed_history(session)
    result = service(session).create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)
    session.commit()

    assert result.outcome is SnapshotOutcome.CREATED
    assert result.snapshot.revision == 1
    assert result.snapshot.applied_transaction_count == 2
    cash = session.scalar(
        select(SnapshotCash).where(SnapshotCash.snapshot_id == result.snapshot.id)
    )
    position = session.scalar(
        select(SnapshotPosition).where(SnapshotPosition.snapshot_id == result.snapshot.id)
    )
    assert cash is not None and cash.amount == Decimal("800.0000")
    assert position is not None and position.quantity == Decimal("10.000000000000")
    assert position.total_cost_basis == Decimal("200.0000")
    assert Decimal(result.snapshot.canonical_state["cash"]) == Decimal("800")


def test_identical_snapshot_request_reuses_current_revision(session: Session) -> None:
    seed_history(session)
    first = service(session).create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)
    second = service(session).create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)

    assert second.outcome is SnapshotOutcome.REUSED
    assert second.snapshot.id == first.snapshot.id
    assert session.scalar(select(func.count()).select_from(PortfolioSnapshot)) == 1


def test_late_effective_transaction_creates_revision_and_old_snapshot_replays(
    session: Session,
) -> None:
    seed_history(session)
    snapshots = service(session)
    first = snapshots.create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)
    post(
        session,
        4,
        TransactionType.CASH_DEPOSIT,
        effective_at=instant(1, 15),
        amount=Decimal("50"),
    )
    second = snapshots.create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF)
    session.commit()

    assert second.outcome is SnapshotOutcome.REVISED
    assert second.snapshot.revision == 2
    assert second.snapshot.supersedes_snapshot_id == first.snapshot.id
    session.refresh(first.snapshot)
    assert first.snapshot.status is SnapshotStatus.SUPERSEDED
    assert second.snapshot.status is SnapshotStatus.CURRENT
    assert Decimal(second.snapshot.canonical_state["cash"]) == Decimal("850")
    assert snapshots.verify(first.snapshot.id).reproducible is True
    assert snapshots.verify(second.snapshot.id).reproducible is True


def test_unknown_cost_basis_persists_as_unknown_not_zero(session: Session) -> None:
    post(
        session,
        1,
        TransactionType.OPENING_POSITION,
        effective_at=instant(1, 1),
        instrument=True,
        quantity=Decimal("100"),
    )
    snapshot = (
        service(session).create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF).snapshot
    )
    position = session.scalar(
        select(SnapshotPosition).where(SnapshotPosition.snapshot_id == snapshot.id)
    )

    assert position is not None
    assert position.cost_basis_status is CostBasisPersistenceStatus.UNKNOWN
    assert position.total_cost_basis is None
    assert position.average_cost is None


def test_historical_snapshots_use_distinct_cutoffs(session: Session) -> None:
    seed_history(session)
    snapshots = service(session)
    early = snapshots.create(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=datetime(2026, 1, 5, 23, 59, tzinfo=UTC),
    ).snapshot
    later = snapshots.create(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        as_of=datetime(2026, 2, 28, 23, 59, tzinfo=UTC),
    ).snapshot

    assert Decimal(early.canonical_state["cash"]) == Decimal("1000")
    assert early.canonical_state["positions"] == []
    assert Decimal(later.canonical_state["cash"]) == Decimal("650")
    assert Decimal(later.canonical_state["positions"][0]["quantity"]) == Decimal("15")


def test_snapshot_creation_has_audit_trail(session: Session) -> None:
    seed_history(session)
    snapshot = (
        service(session).create(fund_id=FUND_ID, account_id=ACCOUNT_ID, as_of=CUTOFF).snapshot
    )
    event = session.scalar(select(AuditEvent).where(AuditEvent.entity_id == snapshot.id))

    assert event is not None
    assert event.action == "PORTFOLIO_SNAPSHOT_CREATED"
    assert event.details["canonical_input_hash"] == snapshot.canonical_input_hash
