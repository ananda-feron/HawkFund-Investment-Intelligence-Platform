from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from app.ledger.types import TransactionStatus, TransactionType
from app.market_data.service import MarketDataService
from app.market_data.types import PriceRequest, ProviderPrice
from app.models import Transaction
from app.valuation.service import HistoricalValuationService
from tests.conftest import ACCOUNT_ID, FUND_ID, INSTRUMENT_ID
from tests.market_data.test_service import FakeProvider


def add_transaction(session, number: int, kind: TransactionType, day: int, **kwargs) -> None:
    instant = datetime(2026, 3, day, 12, tzinfo=UTC)
    session.add(
        Transaction(
            id=UUID(f"90000000-0000-4000-8000-{number:012d}"),
            fund_id=FUND_ID,
            account_id=ACCOUNT_ID,
            transaction_type=kind,
            effective_at=instant,
            recorded_at=instant,
            source="test",
            external_id=str(number),
            fees=Decimal("0"),
            currency="USD",
            trade_date=None,
            settlement_date=None,
            normalized_payload_hash=f"{number:064x}",
            status=TransactionStatus.POSTED,
            import_batch_id=None,
            created_by_user_id=None,
            reverses_transaction_id=None,
            correction_command_id=None,
            description=None,
            source_metadata={},
            **kwargs,
        )
    )


def test_march_31_historical_value_uses_ledger_and_latest_eligible_price(session) -> None:
    add_transaction(session, 1, TransactionType.OPENING_CASH, 1, amount=Decimal("1000"))
    add_transaction(
        session,
        2,
        TransactionType.BUY,
        2,
        instrument_id=INSTRUMENT_ID,
        quantity=Decimal("10"),
        unit_price=Decimal("20"),
    )
    session.commit()
    provider = FakeProvider(
        (
            ProviderPrice("AAPL", datetime(2026, 3, 31, 20, tzinfo=UTC), Decimal("30")),
            ProviderPrice("AAPL", datetime(2026, 4, 1, 20, tzinfo=UTC), Decimal("99")),
        )
    )
    MarketDataService(session).ingest(
        provider,
        PriceRequest(
            ("AAPL",), datetime(2026, 3, 31, tzinfo=UTC), datetime(2026, 4, 2, tzinfo=UTC)
        ),
        datetime(2026, 4, 2, 21, tzinfo=UTC),
    )

    result = HistoricalValuationService(session).value_at(
        FUND_ID, datetime(2026, 3, 31, 23, 59, tzinfo=UTC), timedelta(days=2)
    )

    assert result.cash_value == Decimal("800")
    assert result.securities_value == Decimal("300")
    assert result.portfolio_value == Decimal("1100")
    assert result.unrealized_pnl == Decimal("100")
    assert result.realized_pnl == Decimal("0")
    assert result.positions[0].quote.observed_at == datetime(2026, 3, 31, 20, tzinfo=UTC)
