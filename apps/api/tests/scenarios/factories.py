from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from app.market_data.types import FreshnessStatus, PriceQuote, PriceType
from app.portfolio.types import CostBasisStatus
from app.valuation.types import PositionValuation, ValuationResult
from tests.conftest import ACCOUNT_ID, FUND_ID

AS_OF = datetime(2026, 3, 31, 20, tzinfo=UTC)


def valuation(position_values: tuple[tuple[UUID, str], ...], cash: str = "0") -> ValuationResult:
    positions = tuple(
        position(instrument_id, value, index)
        for index, (instrument_id, value) in enumerate(position_values, start=1)
    )
    securities = sum((item.market_value for item in positions), Decimal("0"))
    cash_value = Decimal(cash)
    return ValuationResult(
        FUND_ID,
        AS_OF,
        "USD",
        cash_value,
        securities,
        cash_value + securities,
        Decimal("0"),
        Decimal("0"),
        positions,
        (),
        "a" * 64,
    )


def position(instrument_id: UUID, value: str, index: int) -> PositionValuation:
    amount = Decimal(value)
    quote = PriceQuote(
        UUID(f"b0000000-0000-4000-8000-{index:012d}"),
        instrument_id,
        "test",
        PriceType.CLOSE,
        AS_OF,
        AS_OF,
        amount,
        "USD",
        str(instrument_id),
        FreshnessStatus.FRESH,
        Decimal("0"),
        {},
    )
    return PositionValuation(
        ACCOUNT_ID,
        instrument_id,
        Decimal("1"),
        amount,
        amount,
        amount,
        Decimal("0"),
        CostBasisStatus.KNOWN,
        quote,
    )
