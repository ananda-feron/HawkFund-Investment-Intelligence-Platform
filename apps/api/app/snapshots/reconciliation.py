import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditEvent,
    PortfolioSnapshot,
    ReconciliationItem,
    ReconciliationObservation,
    ReconciliationRun,
    SnapshotCash,
    SnapshotPosition,
)
from app.snapshots.errors import ReconciliationError
from app.snapshots.types import ReconciliationKind, ReconciliationStatus


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    run: ReconciliationRun
    items: tuple[ReconciliationItem, ...]
    reused: bool


class ReconciliationService:
    def __init__(
        self,
        session: Session,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))

    def record_observation(
        self,
        *,
        fund_id: UUID,
        account_id: UUID,
        as_of: datetime,
        kind: ReconciliationKind,
        reported_value: Decimal,
        source: str,
        external_id: str,
        instrument_id: UUID | None = None,
        import_batch_id: UUID | None = None,
        evidence: dict[str, object] | None = None,
    ) -> ReconciliationObservation:
        if as_of.tzinfo is None:
            raise ReconciliationError("observation as_of must be timezone-aware")
        if not source.strip() or not external_id.strip():
            raise ReconciliationError("source and external_id are required")
        if kind is ReconciliationKind.CASH and instrument_id is not None:
            raise ReconciliationError("cash observation cannot reference an instrument")
        if kind is ReconciliationKind.POSITION:
            if instrument_id is None:
                raise ReconciliationError("position observation requires an instrument")
            if reported_value < 0:
                raise ReconciliationError("reported position cannot be negative")
        existing = self.session.scalar(
            select(ReconciliationObservation).where(
                ReconciliationObservation.fund_id == fund_id,
                ReconciliationObservation.source == source,
                ReconciliationObservation.external_id == external_id,
            )
        )
        if existing is not None:
            if (
                existing.account_id == account_id
                and existing.kind == kind
                and existing.instrument_id == instrument_id
                and existing.reported_value == reported_value
                and _same_instant(existing.as_of, as_of)
            ):
                return existing
            raise ReconciliationError("observation identity conflicts with existing evidence")
        observation = ReconciliationObservation(
            id=uuid4(),
            fund_id=fund_id,
            account_id=account_id,
            as_of=as_of,
            kind=kind,
            instrument_id=instrument_id,
            reported_value=reported_value,
            currency="USD",
            source=source,
            external_id=external_id,
            import_batch_id=import_batch_id,
            evidence=evidence or {},
            recorded_at=self.clock(),
        )
        self.session.add(observation)
        self.session.flush()
        return observation

    def reconcile(
        self,
        *,
        snapshot_id: UUID,
        tolerance: Decimal = Decimal("0"),
        actor_user_id: UUID | None = None,
    ) -> ReconciliationResult:
        if tolerance < 0:
            raise ReconciliationError("tolerance cannot be negative")
        snapshot = self.session.get(PortfolioSnapshot, snapshot_id)
        if snapshot is None:
            raise ReconciliationError("snapshot does not exist")
        observations_statement = select(ReconciliationObservation).where(
            ReconciliationObservation.fund_id == snapshot.fund_id,
            ReconciliationObservation.as_of == snapshot.as_of,
        )
        if snapshot.account_id is not None:
            observations_statement = observations_statement.where(
                ReconciliationObservation.account_id == snapshot.account_id
            )
        observations = self.session.scalars(observations_statement).all()
        evidence_hash = _evidence_hash(observations)
        existing = self.session.scalar(
            select(ReconciliationRun).where(
                ReconciliationRun.snapshot_id == snapshot_id,
                ReconciliationRun.tolerance == tolerance,
                ReconciliationRun.evidence_hash == evidence_hash,
            )
        )
        if existing is not None:
            existing_items = tuple(
                self.session.scalars(
                    select(ReconciliationItem).where(
                        ReconciliationItem.reconciliation_run_id == existing.id
                    )
                )
            )
            return ReconciliationResult(existing, existing_items, reused=True)
        cash = {
            item.account_id: item.amount
            for item in self.session.scalars(
                select(SnapshotCash).where(SnapshotCash.snapshot_id == snapshot.id)
            )
        }
        positions = {
            (item.account_id, item.instrument_id): item.quantity
            for item in self.session.scalars(
                select(SnapshotPosition).where(SnapshotPosition.snapshot_id == snapshot.id)
            )
        }

        run = ReconciliationRun(
            id=uuid4(),
            snapshot_id=snapshot.id,
            tolerance=tolerance,
            evidence_hash=evidence_hash,
            status=ReconciliationStatus.UNAVAILABLE,
            created_at=self.clock(),
            created_by_user_id=actor_user_id,
        )
        self.session.add(run)
        items: list[ReconciliationItem] = []
        for observation in observations:
            if observation.kind is ReconciliationKind.CASH:
                expected = cash.get(observation.account_id, Decimal("0"))
            else:
                assert observation.instrument_id is not None
                expected = positions.get(
                    (observation.account_id, observation.instrument_id), Decimal("0")
                )
            difference = observation.reported_value - expected
            status = (
                ReconciliationStatus.MATCHED
                if abs(difference) <= tolerance
                else ReconciliationStatus.BREACH
            )
            item = ReconciliationItem(
                id=uuid4(),
                reconciliation_run_id=run.id,
                observation_id=observation.id,
                expected_value=expected,
                reported_value=observation.reported_value,
                difference=difference,
                tolerance=tolerance,
                status=status,
            )
            self.session.add(item)
            items.append(item)
        if items:
            run.status = (
                ReconciliationStatus.BREACH
                if any(item.status is ReconciliationStatus.BREACH for item in items)
                else ReconciliationStatus.MATCHED
            )
        self.session.add(
            AuditEvent(
                id=uuid4(),
                fund_id=snapshot.fund_id,
                actor_user_id=actor_user_id,
                action="PORTFOLIO_RECONCILIATION_COMPLETED",
                entity_type="ReconciliationRun",
                entity_id=run.id,
                occurred_at=self.clock(),
                details={
                    "snapshot_id": str(snapshot.id),
                    "status": run.status.value,
                    "tolerance": str(tolerance),
                    "evidence_hash": evidence_hash,
                    "item_count": len(items),
                    "breach_count": sum(
                        item.status is ReconciliationStatus.BREACH for item in items
                    ),
                },
            )
        )
        self.session.flush()
        return ReconciliationResult(run, tuple(items), reused=False)


def _same_instant(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None:
        left = left.replace(tzinfo=UTC)
    if right.tzinfo is None:
        right = right.replace(tzinfo=UTC)
    return left == right


def _evidence_hash(observations: Sequence[ReconciliationObservation]) -> str:
    payload = [
        {
            "id": str(item.id),
            "account_id": str(item.account_id),
            "kind": item.kind.value,
            "instrument_id": (None if item.instrument_id is None else str(item.instrument_id)),
            "reported_value": str(item.reported_value),
            "source": item.source,
            "external_id": item.external_id,
        }
        for item in sorted(observations, key=lambda observation: str(observation.id))
    ]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
