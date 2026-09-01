from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ledger.types import ImportRecordStatus
from app.models import ImportBatch, ImportRecord


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    transaction_id: UUID
    batch_id: UUID
    source: str
    external_id: str
    filename: str | None
    content_sha256: str
    row_number: int
    source_locator: str
    status: ImportRecordStatus
    received_at: datetime
    raw_payload: dict[str, object]
    normalized_payload: dict[str, object] | None


class ProvenanceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def for_transaction(self, transaction_id: UUID) -> tuple[ProvenanceRecord, ...]:
        rows = self.session.execute(
            select(ImportRecord, ImportBatch)
            .join(ImportBatch, ImportBatch.id == ImportRecord.import_batch_id)
            .where(ImportRecord.transaction_id == transaction_id)
            .order_by(ImportBatch.received_at, ImportRecord.row_number)
        ).all()
        return tuple(
            ProvenanceRecord(
                transaction_id=transaction_id,
                batch_id=batch.id,
                source=batch.source,
                external_id=str(record.raw_payload.get("external_id", "")),
                filename=batch.filename,
                content_sha256=batch.content_sha256,
                row_number=record.row_number,
                source_locator=record.source_locator,
                status=record.status,
                received_at=batch.received_at,
                raw_payload=record.raw_payload,
                normalized_payload=record.normalized_payload,
            )
            for record, batch in rows
        )
