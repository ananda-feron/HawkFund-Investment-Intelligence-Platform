from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.ledger.types import TransactionType
from app.market_data.types import FreshnessStatus, PriceQuote, PriceType
from app.portfolio.engine import PortfolioEngine
from app.portfolio.types import LedgerTransaction
from app.valuation.engine import RealizedPnlEngine, ValuationEngine
from tests.conftest import ACCOUNT_ID, FUND_ID, INSTRUMENT_ID


def transaction(number: int, kind: TransactionType, day: int, **kwargs) -> LedgerTransaction:
    instant = datetime(2026, 3, day, 12, tzinfo=UTC)
    return LedgerTransaction(
        id=UUID(f"70000000-0000-4000-8000-{number:012d}"),
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        transaction_type=kind,
        effective_at=instant,
        recorded_at=instant,
        source="test",
        external_id=str(number),
        **kwargs,
    )


def quote(price: str, stale: bool = False) -> PriceQuote:
    return PriceQuote(
        UUID("80000000-0000-4000-8000-000000000001"),
        INSTRUMENT_ID,
        "fake",
        PriceType.CLOSE,
        datetime(2026, 3, 31, tzinfo=UTC),
        datetime(2026, 3, 31, tzinfo=UTC),
        Decimal(price),
        "USD",
        "AAPL",
        FreshnessStatus.STALE if stale else FreshnessStatus.FRESH,
        Decimal("0"),
        {},
    )


def test_market_cash_portfolio_and_trade_pnl_are_deterministic() -> None:
    transactions = (
        transaction(1, TransactionType.OPENING_CASH, 1, amount=Decimal("1000")),
        transaction(
            2,
            TransactionType.BUY,
            2,
            instrument_id=INSTRUMENT_ID,
            quantity=Decimal("10"),
            unit_price=Decimal("20"),
        ),
        transaction(
            3,
            TransactionType.SELL,
            10,
            instrument_id=INSTRUMENT_ID,
            quantity=Decimal("4"),
            unit_price=Decimal("25"),
        ),
    )
    as_of = datetime(2026, 3, 31, 23, tzinfo=UTC)
    state = PortfolioEngine().reconstruct(FUND_ID, transactions, as_of)
    realized = RealizedPnlEngine().calculate(FUND_ID, transactions, as_of)

    result = ValuationEngine().value(state, {INSTRUMENT_ID: quote("30")}, realized)

    assert result.cash_value == Decimal("900")
    assert result.securities_value == Decimal("180")
    assert result.portfolio_value == Decimal("1080")
    assert result.unrealized_pnl == Decimal("60")
    assert result.realized_pnl == Decimal("20")
    assert result == ValuationEngine().value(state, {INSTRUMENT_ID: quote("30")}, realized)


def test_stale_quote_warns_and_unknown_basis_propagates() -> None:
    transactions = (
        transaction(1, TransactionType.OPENING_CASH, 1, amount=Decimal("1000")),
        transaction(
            2,
            TransactionType.OPENING_POSITION,
            2,
            instrument_id=INSTRUMENT_ID,
            quantity=Decimal("10"),
        ),
    )
    as_of = datetime(2026, 3, 31, 23, tzinfo=UTC)
    state = PortfolioEngine().reconstruct(FUND_ID, transactions, as_of)
    result = ValuationEngine().value(
        state,
        {INSTRUMENT_ID: quote("30", stale=True)},
        RealizedPnlEngine().calculate(FUND_ID, transactions, as_of),
    )
    assert result.unrealized_pnl is None
    assert any("stale price" in warning for warning in result.warnings)
