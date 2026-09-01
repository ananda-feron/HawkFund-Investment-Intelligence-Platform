import hashlib
import json
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.commands import CreateTransaction
from app.ledger.errors import OpeningBalanceError, ReversalError, TransactionValidationError
from app.ledger.repository import TransactionRepository
from app.ledger.validation import validate_transaction
from app.models import (
    ImportBatch,
    ImportConflict,
    Transaction,
    TransactionStatus,
    TransactionType,
)


class CreationStatus(str, Enum):
    CREATED = "CREATED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True, slots=True)
class CreationResult:
    status: CreationStatus
    transaction: Transaction
    conflict: ImportConflict | None = None


class TransactionService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = TransactionRepository(session)

    def create(self, command: CreateTransaction) -> CreationResult:
        payload = command.canonical_payload()
        payload_hash = _payload_hash(command.economic_payload())
        validate_transaction(command)
        self._validate_import_batch(command)
        existing = self.repository.by_source_identity(
            command.fund_id, command.source, command.external_id
        )
        if existing is not None:
            if existing.normalized_payload_hash == payload_hash:
                return CreationResult(CreationStatus.DUPLICATE, existing)
            return self._record_conflict(command, payload, payload_hash, existing)

        self._validate_opening_order(command)
        target = self._validate_reversal(command)
        values = {field.name: getattr(command, field.name) for field in fields(command)}
        values["source_metadata"] = command.source_metadata or {}
        transaction = Transaction(
            id=uuid4(),
            normalized_payload_hash=payload_hash,
            status=TransactionStatus.POSTED,
            **values,
        )
        self.repository.add(transaction)
        if target is not None:
            target.status = TransactionStatus.REVERSED
            self.session.flush()
        return CreationResult(CreationStatus.CREATED, transaction)

    def _validate_import_batch(self, command: CreateTransaction) -> None:
        if command.import_batch_id is None:
            return
        batch = self.session.get(ImportBatch, command.import_batch_id)
        if batch is None:
            raise TransactionValidationError("import batch does not exist")
        if batch.fund_id != command.fund_id or batch.source != command.source:
            raise TransactionValidationError("import batch must belong to the same fund and source")

    def _validate_opening_order(self, command: CreateTransaction) -> None:
        if command.transaction_type is TransactionType.OPENING_CASH:
            if self.repository.has_posted_cash_activity(command.account_id):
                raise OpeningBalanceError(
                    "opening cash must be the account's first posted activity"
                )
        elif command.transaction_type is TransactionType.OPENING_POSITION:
            assert command.instrument_id is not None
            if self.repository.has_posted_quantity_activity(
                command.account_id, command.instrument_id
            ):
                raise OpeningBalanceError(
                    "opening position must be the account/instrument's first posted activity"
                )

    def _validate_reversal(self, command: CreateTransaction) -> Transaction | None:
        if command.transaction_type is not TransactionType.REVERSAL:
            return None
        assert command.reverses_transaction_id is not None
        target = self.repository.by_id(command.reverses_transaction_id)
        if target is None:
            raise ReversalError("reversal target does not exist")
        if target.transaction_type is TransactionType.REVERSAL:
            raise ReversalError("a reversal cannot target another reversal")
        if target.fund_id != command.fund_id or target.account_id != command.account_id:
            raise ReversalError("reversal target must belong to the same fund and account")
        if self.repository.reversal_for(target.id) is not None:
            raise ReversalError("transaction has already been reversed")
        return target

    def _record_conflict(
        self,
        command: CreateTransaction,
        payload: dict[str, object],
        payload_hash: str,
        existing: Transaction,
    ) -> CreationResult:
        if command.import_batch_id is None:
            return CreationResult(CreationStatus.CONFLICT, existing)
        prior = self.session.scalar(
            select(ImportConflict).where(
                ImportConflict.import_batch_id == command.import_batch_id,
                ImportConflict.source == command.source,
                ImportConflict.external_id == command.external_id,
                ImportConflict.incoming_payload_hash == payload_hash,
            )
        )
        if prior is not None:
            return CreationResult(CreationStatus.CONFLICT, existing, prior)
        conflict = ImportConflict(
            id=uuid4(),
            fund_id=command.fund_id,
            import_batch_id=command.import_batch_id,
            existing_transaction_id=existing.id,
            source=command.source,
            external_id=command.external_id,
            existing_payload_hash=existing.normalized_payload_hash,
            incoming_payload_hash=payload_hash,
            incoming_payload=payload,
            detected_at=datetime.now(UTC),
        )
        self.session.add(conflict)
        batch = self.session.get_one(ImportBatch, command.import_batch_id)
        batch.conflict_count += 1
        self.session.flush()
        return CreationResult(CreationStatus.CONFLICT, existing, conflict)


def _payload_hash(payload: dict[str, object]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()
