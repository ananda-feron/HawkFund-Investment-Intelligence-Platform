from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.ledger.types import TransactionType
from app.portfolio.types import LedgerTransaction

FUND_ID = UUID("10000000-0000-4000-8000-000000000001")
OTHER_FUND_ID = UUID("10000000-0000-4000-8000-000000000002")
ACCOUNT_ID = UUID("50000000-0000-4000-8000-000000000001")
OTHER_ACCOUNT_ID = UUID("50000000-0000-4000-8000-000000000002")
AAPL_ID = UUID("40000000-0000-4000-8000-000000000001")
MSFT_ID = UUID("40000000-0000-4000-8000-000000000002")


def at(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def transaction(
    sequence: int,
    kind: TransactionType,
    *,
    effective_at: datetime | None = None,
    recorded_at: datetime | None = None,
    fund_id: UUID = FUND_ID,
    account_id: UUID = ACCOUNT_ID,
    instrument_id: UUID | None = None,
    quantity: Decimal | None = None,
    unit_price: Decimal | None = None,
    amount: Decimal | None = None,
    fees: Decimal = Decimal("0"),
    reverses: UUID | None = None,
) -> LedgerTransaction:
    effective = effective_at or at(sequence)
    return LedgerTransaction(
        id=UUID(int=sequence),
        fund_id=fund_id,
        account_id=account_id,
        transaction_type=kind,
        effective_at=effective,
        recorded_at=recorded_at or effective,
        source="phase1_fixture",
        external_id=f"TX-{sequence:03d}",
        instrument_id=instrument_id,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        fees=fees,
        reverses_transaction_id=reverses,
    )
