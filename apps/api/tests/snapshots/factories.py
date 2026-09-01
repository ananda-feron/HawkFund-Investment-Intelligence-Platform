from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.ledger.commands import CreateTransaction
from app.ledger.service import TransactionService
from app.ledger.types import TransactionType
from app.models import Transaction
from tests.conftest import ACCOUNT_ID, BATCH_ID, FUND_ID, INSTRUMENT_ID


def instant(month: int, day: int) -> datetime:
    return datetime(2026, month, day, 16, tzinfo=UTC)


def post(
    session: Session,
    sequence: int,
    kind: TransactionType,
    *,
    effective_at: datetime,
    instrument: bool = False,
    quantity: Decimal | None = None,
    unit_price: Decimal | None = None,
    amount: Decimal | None = None,
    fees: Decimal = Decimal("0"),
) -> Transaction:
    result = TransactionService(session).create(
        CreateTransaction(
            fund_id=FUND_ID,
            account_id=ACCOUNT_ID,
            transaction_type=kind,
            effective_at=effective_at,
            recorded_at=instant(3, 1),
            source="hawkfund_csv",
            external_id=f"SNAP-{sequence:03d}",
            instrument_id=INSTRUMENT_ID if instrument else None,
            quantity=quantity,
            unit_price=unit_price,
            amount=amount,
            fees=fees,
            import_batch_id=BATCH_ID,
        )
    )
    return result.transaction
