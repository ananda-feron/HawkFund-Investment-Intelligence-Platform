from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.csv_provider import CsvMarketDataProvider
from app.market_data.types import PriceRequest


def test_csv_provider_normalizes_and_filters_rows() -> None:
    content = """identifier,observed_at,price,currency,price_type
AAPL,2026-03-31T20:00:00Z,30.25,USD,CLOSE
MSFT,2026-03-31T20:00:00Z,50,USD,CLOSE
AAPL,2026-04-01T20:00:00Z,99,USD,CLOSE
"""
    request = PriceRequest(
        ("AAPL",), datetime(2026, 3, 31, tzinfo=UTC), datetime(2026, 3, 31, 23, tzinfo=UTC)
    )

    rows = CsvMarketDataProvider(content, "custodian_csv").fetch_prices(request)

    assert len(rows) == 1
    assert rows[0].price == Decimal("30.25")
    assert rows[0].source_metadata == {"row_number": 2}
