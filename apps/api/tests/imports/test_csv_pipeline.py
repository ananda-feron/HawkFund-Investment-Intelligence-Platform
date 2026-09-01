from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.imports import CsvTransactionImporter, ProvenanceService
from app.ledger.types import ImportBatchStatus, ImportRecordStatus
from app.models import AuditEvent, ImportBatch, ImportConflict, ImportRecord, Transaction
from tests.conftest import ACCOUNT_ID, FUND_ID

NOW = datetime(2026, 2, 1, 12, tzinfo=UTC)
HEADERS = (
    "external_id,transaction_type,effective_at,instrument_symbol,quantity,"
    "unit_price,amount,fees,currency,description\n"
)


def importer(session: Session) -> CsvTransactionImporter:
    return CsvTransactionImporter(session, clock=lambda: NOW)


def valid_content(quantity: str = "10", description: str = "initial") -> str:
    return (
        HEADERS
        + f"TX-100, buy ,2026-01-10T16:00:00Z, aapl ,{quantity},20,,1,USD,{description}\n"
        + "TX-101,CASH_DEPOSIT,2026-01-09T16:00:00+00:00,,,,1000,,USD,funding\n"
    )


def run_import(session: Session, content: str, filename: str = "ledger.csv"):
    return importer(session).import_text(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        source="hawkfund_csv",
        filename=filename,
        content=content,
    )


def test_csv_is_normalized_validated_and_posted(session: Session) -> None:
    report = run_import(session, valid_content())
    session.commit()

    assert report.status is ImportBatchStatus.COMPLETED
    assert report.total_count == 2
    assert report.posted_count == 2
    transactions = session.scalars(select(Transaction).order_by(Transaction.external_id)).all()
    assert len(transactions) == 2
    assert transactions[0].external_id == "TX-100"
    assert str(transactions[0].quantity) == "10.000000000000"
    assert transactions[0].instrument_id == UUID("40000000-0000-4000-8000-000000000001")
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 1


def test_invalid_rows_are_rejected_without_blocking_valid_rows(session: Session) -> None:
    content = (
        HEADERS
        + "BAD-1,BUY,not-a-date,AAPL,10,20,,0,USD,bad date\n"
        + "GOOD-1,CASH_DEPOSIT,2026-01-09T00:00:00Z,,,,100,,USD,good\n"
        + "BAD-2,BUY,2026-01-10T00:00:00Z,UNKNOWN,10,20,,0,USD,bad symbol\n"
    )
    report = run_import(session, content)
    session.commit()

    assert report.status is ImportBatchStatus.COMPLETED_WITH_ERRORS
    assert report.total_count == 3
    assert report.posted_count == 1
    assert report.rejected_count == 2
    records = session.scalars(select(ImportRecord).order_by(ImportRecord.row_number)).all()
    assert [item.status for item in records] == [
        ImportRecordStatus.REJECTED,
        ImportRecordStatus.POSTED,
        ImportRecordStatus.REJECTED,
    ]
    assert records[0].error_code == "INVALID_DATETIME"
    assert records[2].error_code == "UNKNOWN_INSTRUMENT"


def test_same_file_is_batch_idempotent(session: Session) -> None:
    first = run_import(session, valid_content())
    second = run_import(session, valid_content())
    session.commit()

    assert second.reused_batch is True
    assert second.batch_id == first.batch_id
    assert session.scalar(select(func.count()).select_from(ImportBatch)) == 2
    assert session.scalar(select(func.count()).select_from(Transaction)) == 2
    assert session.scalar(select(func.count()).select_from(ImportRecord)) == 2


def test_different_file_with_same_economics_is_transaction_idempotent(
    session: Session,
) -> None:
    first = run_import(session, valid_content(description="first"), "first.csv")
    second = run_import(session, valid_content(description="second"), "second.csv")
    session.commit()

    assert first.posted_count == 2
    assert second.duplicate_count == 2
    assert session.scalar(select(func.count()).select_from(Transaction)) == 2
    assert session.scalar(select(func.count()).select_from(ImportRecord)) == 4


def test_changed_economics_records_conflict_and_preserves_original(
    session: Session,
) -> None:
    run_import(session, valid_content(quantity="10"), "first.csv")
    report = run_import(session, valid_content(quantity="20"), "changed.csv")
    session.commit()

    assert report.conflict_count == 1
    original = session.scalar(select(Transaction).where(Transaction.external_id == "TX-100"))
    assert original is not None
    assert str(original.quantity) == "10.000000000000"
    assert session.scalar(select(func.count()).select_from(ImportConflict)) == 1
    conflict_record = session.scalar(
        select(ImportRecord).where(ImportRecord.status == ImportRecordStatus.CONFLICT)
    )
    assert conflict_record is not None
    assert conflict_record.import_conflict_id is not None


def test_transaction_provenance_traces_every_source_occurrence(session: Session) -> None:
    run_import(session, valid_content(description="first"), "first.csv")
    run_import(session, valid_content(description="second"), "second.csv")
    transaction = session.scalar(select(Transaction).where(Transaction.external_id == "TX-100"))
    assert transaction is not None

    provenance = ProvenanceService(session).for_transaction(transaction.id)

    assert len(provenance) == 2
    assert {item.filename for item in provenance} == {"first.csv", "second.csv"}
    assert {item.status for item in provenance} == {
        ImportRecordStatus.POSTED,
        ImportRecordStatus.DUPLICATE,
    }
    assert all(item.source == "hawkfund_csv" for item in provenance)
    assert all(item.raw_payload["external_id"] == "TX-100" for item in provenance)
