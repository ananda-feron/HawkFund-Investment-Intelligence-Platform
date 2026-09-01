import csv
import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.imports.errors import ImportPipelineError, RowNormalizationError
from app.ledger.commands import CreateTransaction
from app.ledger.errors import LedgerError
from app.ledger.service import CreationStatus, TransactionService
from app.ledger.types import ImportBatchStatus, ImportRecordStatus, TransactionType
from app.models import AuditEvent, ImportBatch, ImportRecord, Instrument

REQUIRED_COLUMNS = {"external_id", "transaction_type", "effective_at"}


@dataclass(frozen=True, slots=True)
class ImportReport:
    batch_id: UUID
    status: ImportBatchStatus
    total_count: int
    posted_count: int
    duplicate_count: int
    rejected_count: int
    conflict_count: int
    reused_batch: bool


class CsvTransactionImporter:
    def __init__(
        self,
        session: Session,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.session = session
        self.clock = clock or (lambda: datetime.now(UTC))

    def import_text(
        self,
        *,
        fund_id: UUID,
        account_id: UUID,
        source: str,
        filename: str,
        content: str,
        parser_version: str = "csv-v1",
        initiated_by_user_id: UUID | None = None,
    ) -> ImportReport:
        if not source.strip():
            raise ImportPipelineError("source is required")
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        existing = self.session.scalar(
            select(ImportBatch).where(
                ImportBatch.fund_id == fund_id,
                ImportBatch.source == source,
                ImportBatch.content_sha256 == content_hash,
            )
        )
        if existing is not None:
            return self._report(existing, reused=True)

        reader = csv.DictReader(io.StringIO(content))
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ImportPipelineError(f"missing required CSV columns: {', '.join(sorted(missing))}")

        now = self.clock()
        batch = ImportBatch(
            id=uuid4(),
            fund_id=fund_id,
            source=source,
            filename=filename,
            content_sha256=content_hash,
            parser_version=parser_version,
            status=ImportBatchStatus.PROCESSING,
            initiated_by_user_id=initiated_by_user_id,
            received_at=now,
            completed_at=None,
            total_count=0,
            posted_count=0,
            duplicate_count=0,
            rejected_count=0,
            conflict_count=0,
            failure_summary=None,
        )
        self.session.add(batch)
        self.session.flush()

        counts = {status: 0 for status in ImportRecordStatus}
        transaction_service = TransactionService(self.session)
        for row_number, source_row in enumerate(reader, start=2):
            raw = {key: value or "" for key, value in source_row.items() if key is not None}
            record = ImportRecord(
                id=uuid4(),
                import_batch_id=batch.id,
                row_number=row_number,
                source_locator=f"{filename}:row:{row_number}",
                raw_payload=raw,
                normalized_payload=None,
                raw_payload_hash=_hash_payload(raw),
                status=ImportRecordStatus.RECEIVED,
                transaction_id=None,
                import_conflict_id=None,
                error_code=None,
                error_message=None,
                created_at=now,
            )
            self.session.add(record)
            try:
                command = self._normalize(
                    raw,
                    fund_id=fund_id,
                    account_id=account_id,
                    source=source,
                    batch_id=batch.id,
                    row_number=row_number,
                    recorded_at=now,
                )
                record.normalized_payload = command.canonical_payload()
                record.status = ImportRecordStatus.NORMALIZED
                result = transaction_service.create(command)
                record.transaction_id = result.transaction.id
                if result.status is CreationStatus.CREATED:
                    record.status = ImportRecordStatus.POSTED
                elif result.status is CreationStatus.DUPLICATE:
                    record.status = ImportRecordStatus.DUPLICATE
                else:
                    record.status = ImportRecordStatus.CONFLICT
                    record.import_conflict_id = (
                        result.conflict.id if result.conflict is not None else None
                    )
            except (LedgerError, RowNormalizationError) as error:
                record.status = ImportRecordStatus.REJECTED
                record.error_code = getattr(error, "code", "VALIDATION_ERROR")
                record.error_message = str(error)[:1000]
            counts[record.status] += 1

        batch.total_count = sum(counts.values())
        batch.posted_count = counts[ImportRecordStatus.POSTED]
        batch.duplicate_count = counts[ImportRecordStatus.DUPLICATE]
        batch.rejected_count = counts[ImportRecordStatus.REJECTED]
        batch.conflict_count = counts[ImportRecordStatus.CONFLICT]
        batch.completed_at = self.clock()
        if batch.rejected_count or batch.conflict_count:
            batch.status = ImportBatchStatus.COMPLETED_WITH_ERRORS
        else:
            batch.status = ImportBatchStatus.COMPLETED
        self.session.add(
            AuditEvent(
                id=uuid4(),
                fund_id=fund_id,
                actor_user_id=initiated_by_user_id,
                action="IMPORT_BATCH_COMPLETED",
                entity_type="ImportBatch",
                entity_id=batch.id,
                occurred_at=batch.completed_at,
                details={
                    "source": source,
                    "content_sha256": content_hash,
                    "total_count": batch.total_count,
                    "posted_count": batch.posted_count,
                    "duplicate_count": batch.duplicate_count,
                    "rejected_count": batch.rejected_count,
                    "conflict_count": batch.conflict_count,
                },
            )
        )
        self.session.flush()
        return self._report(batch, reused=False)

    def _normalize(
        self,
        raw: dict[str, str],
        *,
        fund_id: UUID,
        account_id: UUID,
        source: str,
        batch_id: UUID,
        row_number: int,
        recorded_at: datetime,
    ) -> CreateTransaction:
        external_id = _required(raw, "external_id")
        try:
            transaction_type = TransactionType(_required(raw, "transaction_type").upper())
        except ValueError as error:
            raise RowNormalizationError(
                "UNSUPPORTED_TRANSACTION_TYPE",
                f"unsupported transaction type: {raw.get('transaction_type', '')}",
            ) from error
        effective_at = _datetime(_required(raw, "effective_at"), "effective_at")
        symbol = _optional(raw, "instrument_symbol")
        instrument_id = self._instrument_id(symbol) if symbol else None
        return CreateTransaction(
            fund_id=fund_id,
            account_id=account_id,
            transaction_type=transaction_type,
            effective_at=effective_at,
            recorded_at=recorded_at,
            source=source,
            external_id=external_id,
            instrument_id=instrument_id,
            quantity=_decimal(raw, "quantity"),
            unit_price=_decimal(raw, "unit_price"),
            amount=_decimal(raw, "amount"),
            fees=_decimal(raw, "fees") or Decimal("0"),
            currency=_optional(raw, "currency") or "USD",
            import_batch_id=batch_id,
            description=_optional(raw, "description"),
            source_metadata={"row_number": row_number},
        )

    def _instrument_id(self, symbol: str) -> UUID:
        matches = self.session.scalars(
            select(Instrument).where(func.upper(Instrument.symbol) == symbol.upper())
        ).all()
        if not matches:
            raise RowNormalizationError("UNKNOWN_INSTRUMENT", f"unknown instrument: {symbol}")
        if len(matches) > 1:
            raise RowNormalizationError(
                "AMBIGUOUS_INSTRUMENT", f"instrument symbol is ambiguous: {symbol}"
            )
        return matches[0].id

    def _report(self, batch: ImportBatch, *, reused: bool) -> ImportReport:
        return ImportReport(
            batch_id=batch.id,
            status=batch.status,
            total_count=batch.total_count,
            posted_count=batch.posted_count,
            duplicate_count=batch.duplicate_count,
            rejected_count=batch.rejected_count,
            conflict_count=batch.conflict_count,
            reused_batch=reused,
        )


def _required(raw: dict[str, str], field: str) -> str:
    value = _optional(raw, field)
    if value is None:
        raise RowNormalizationError("MISSING_FIELD", f"{field} is required")
    return value


def _optional(raw: dict[str, str], field: str) -> str | None:
    value = raw.get(field, "").strip()
    return value or None


def _decimal(raw: dict[str, str], field: str) -> Decimal | None:
    value = _optional(raw, field)
    if value is None:
        return None
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation as error:
        raise RowNormalizationError("INVALID_DECIMAL", f"invalid {field}: {value}") from error


def _datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RowNormalizationError("INVALID_DATETIME", f"invalid {field}: {value}") from error
    if parsed.tzinfo is None:
        raise RowNormalizationError("NAIVE_DATETIME", f"{field} must include a timezone")
    return parsed


def _hash_payload(payload: dict[str, str]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
