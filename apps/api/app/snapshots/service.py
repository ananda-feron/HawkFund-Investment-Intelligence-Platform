from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.types import TransactionType
from app.models import (
    AuditEvent,
    PortfolioSnapshot,
    SnapshotCash,
    SnapshotPosition,
    Transaction,
)
from app.portfolio import LedgerTransaction, PortfolioEngine
from app.snapshots.errors import SnapshotError
from app.snapshots.types import CostBasisPersistenceStatus, SnapshotStatus


class SnapshotOutcome(str, Enum):
    CREATED = "CREATED"
    REUSED = "REUSED"
    REVISED = "REVISED"


@dataclass(frozen=True, slots=True)
class SnapshotResult:
    outcome: SnapshotOutcome
    snapshot: PortfolioSnapshot


@dataclass(frozen=True, slots=True)
class SnapshotVerification:
    snapshot_id: UUID
    reproducible: bool
    expected_input_hash: str
    actual_input_hash: str


class SnapshotService:
    def __init__(
        self,
        session: Session,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))
        self.engine = PortfolioEngine()

    def create(
        self,
        *,
        fund_id: UUID,
        as_of: datetime,
        account_id: UUID | None = None,
        actor_user_id: UUID | None = None,
    ) -> SnapshotResult:
        transactions = self._ledger(fund_id, account_id)
        state = self.engine.reconstruct(fund_id, transactions, as_of, account_id)
        canonical_state = state.canonical_dict()
        current = self._current(fund_id, account_id, as_of)
        if (
            current is not None
            and current.canonical_input_hash == state.metadata.canonical_input_hash
            and current.canonical_state == canonical_state
        ):
            return SnapshotResult(SnapshotOutcome.REUSED, current)

        outcome = SnapshotOutcome.CREATED
        revision = 1
        supersedes_id = None
        if current is not None:
            current.status = SnapshotStatus.SUPERSEDED
            revision = current.revision + 1
            supersedes_id = current.id
            outcome = SnapshotOutcome.REVISED

        snapshot = PortfolioSnapshot(
            id=uuid4(),
            fund_id=fund_id,
            account_id=account_id,
            as_of=as_of,
            revision=revision,
            status=SnapshotStatus.CURRENT,
            calculation_version=state.metadata.calculation_version,
            canonical_input_hash=state.metadata.canonical_input_hash,
            canonical_state=canonical_state,
            applied_transaction_count=state.metadata.applied_transaction_count,
            last_applied_transaction_id=state.metadata.last_applied_transaction_id,
            supersedes_snapshot_id=supersedes_id,
            created_at=self.clock(),
        )
        self.session.add(snapshot)
        self.session.flush()
        self.session.add_all(
            [
                SnapshotCash(
                    id=uuid4(),
                    snapshot_id=snapshot.id,
                    account_id=item.account_id,
                    currency=item.currency,
                    amount=item.amount,
                )
                for item in state.cash_by_account
            ]
        )
        self.session.add_all(
            [
                SnapshotPosition(
                    id=uuid4(),
                    snapshot_id=snapshot.id,
                    account_id=item.account_id,
                    instrument_id=item.instrument_id,
                    quantity=item.quantity,
                    total_cost_basis=item.total_cost_basis,
                    average_cost=item.average_cost,
                    cost_basis_status=CostBasisPersistenceStatus(item.cost_basis_status.value),
                    source_transaction_ids=[
                        str(transaction_id) for transaction_id in item.source_transaction_ids
                    ],
                )
                for item in state.positions
            ]
        )
        self.session.add(
            AuditEvent(
                id=uuid4(),
                fund_id=fund_id,
                actor_user_id=actor_user_id,
                action="PORTFOLIO_SNAPSHOT_CREATED",
                entity_type="PortfolioSnapshot",
                entity_id=snapshot.id,
                occurred_at=self.clock(),
                details={
                    "revision": revision,
                    "as_of": as_of.isoformat(),
                    "canonical_input_hash": state.metadata.canonical_input_hash,
                    "supersedes_snapshot_id": (
                        None if supersedes_id is None else str(supersedes_id)
                    ),
                },
            )
        )
        self.session.flush()
        return SnapshotResult(outcome, snapshot)

    def verify(self, snapshot_id: UUID) -> SnapshotVerification:
        snapshot = self.session.get(PortfolioSnapshot, snapshot_id)
        if snapshot is None:
            raise SnapshotError("snapshot does not exist")
        metadata = snapshot.canonical_state.get("metadata")
        if not isinstance(metadata, dict):
            raise SnapshotError("snapshot metadata is missing")
        raw_ids = metadata.get("applied_transaction_ids")
        raw_as_of = metadata.get("as_of")
        if not isinstance(raw_ids, list) or not isinstance(raw_as_of, str):
            raise SnapshotError("snapshot replay metadata is invalid")
        transaction_ids = [UUID(value) for value in raw_ids]
        transactions = self._ledger_by_ids(transaction_ids)
        as_of = datetime.fromisoformat(raw_as_of)
        state = self.engine.reconstruct(snapshot.fund_id, transactions, as_of, snapshot.account_id)
        return SnapshotVerification(
            snapshot_id=snapshot.id,
            reproducible=(
                state.metadata.canonical_input_hash == snapshot.canonical_input_hash
                and state.canonical_dict() == snapshot.canonical_state
            ),
            expected_input_hash=snapshot.canonical_input_hash,
            actual_input_hash=state.metadata.canonical_input_hash,
        )

    def _ledger(self, fund_id: UUID, account_id: UUID | None) -> tuple[LedgerTransaction, ...]:
        statement = select(Transaction).where(Transaction.fund_id == fund_id)
        if account_id is not None:
            statement = statement.where(Transaction.account_id == account_id)
        return tuple(_domain_transaction(item) for item in self.session.scalars(statement))

    def _ledger_by_ids(self, transaction_ids: list[UUID]) -> tuple[LedgerTransaction, ...]:
        if not transaction_ids:
            return ()
        rows = self.session.scalars(
            select(Transaction).where(Transaction.id.in_(transaction_ids))
        ).all()
        if len(rows) != len(transaction_ids):
            raise SnapshotError("snapshot ledger evidence is incomplete")
        return tuple(_domain_transaction(item) for item in rows)

    def _current(
        self, fund_id: UUID, account_id: UUID | None, as_of: datetime
    ) -> PortfolioSnapshot | None:
        statement = select(PortfolioSnapshot).where(
            PortfolioSnapshot.fund_id == fund_id,
            PortfolioSnapshot.as_of == as_of,
            PortfolioSnapshot.status == SnapshotStatus.CURRENT,
        )
        if account_id is None:
            statement = statement.where(PortfolioSnapshot.account_id.is_(None))
        else:
            statement = statement.where(PortfolioSnapshot.account_id == account_id)
        return self.session.scalar(statement)


def _domain_transaction(transaction: Transaction) -> LedgerTransaction:
    return LedgerTransaction(
        id=transaction.id,
        fund_id=transaction.fund_id,
        account_id=transaction.account_id,
        transaction_type=TransactionType(transaction.transaction_type),
        effective_at=_as_utc(transaction.effective_at),
        recorded_at=_as_utc(transaction.recorded_at),
        source=transaction.source,
        external_id=transaction.external_id,
        instrument_id=transaction.instrument_id,
        quantity=transaction.quantity,
        unit_price=transaction.unit_price,
        amount=transaction.amount,
        fees=transaction.fees,
        currency=transaction.currency,
        trade_date=transaction.trade_date,
        settlement_date=transaction.settlement_date,
        reverses_transaction_id=transaction.reverses_transaction_id,
    )


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
