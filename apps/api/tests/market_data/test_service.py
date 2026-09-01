from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market_data.errors import InvalidPriceObservation, MissingPriceError
from app.market_data.service import MarketDataService
from app.market_data.types import (
    FreshnessStatus,
    PriceIngestionStatus,
    PriceRequest,
    ProviderPrice,
)
from tests.conftest import INSTRUMENT_ID


@dataclass
class FakeProvider:
    prices: tuple[ProviderPrice, ...]
    name: str = "fake"

    def fetch_prices(self, request: PriceRequest) -> tuple[ProviderPrice, ...]:
        return self.prices


def request(start_day: int = 30) -> PriceRequest:
    return PriceRequest(
        ("AAPL",), datetime(2026, 3, start_day, tzinfo=UTC), datetime(2026, 3, 31, tzinfo=UTC)
    )


def test_ingestion_is_idempotent_and_retains_provenance(session) -> None:
    observed = datetime(2026, 3, 31, 20, tzinfo=UTC)
    provider = FakeProvider(
        (ProviderPrice("AAPL", observed, Decimal("30"), source_metadata={"vendor_row": "7"}),)
    )
    service = MarketDataService(session)

    first = service.ingest(provider, request(), datetime(2026, 4, 1, tzinfo=UTC))
    second = service.ingest(provider, request(), datetime(2026, 4, 2, tzinfo=UTC))

    assert first.batch_id == second.batch_id
    assert first.inserted_count == 1
    quote = service.latest_quote(INSTRUMENT_ID, datetime(2026, 4, 1, tzinfo=UTC), timedelta(days=2))
    assert quote.price == Decimal("30")
    assert quote.source_metadata == {"vendor_row": "7"}
    assert quote.freshness is FreshnessStatus.FRESH


def test_conflicting_observation_is_preserved_not_overwritten(session) -> None:
    observed = datetime(2026, 3, 31, 20, tzinfo=UTC)
    service = MarketDataService(session)
    service.ingest(
        FakeProvider((ProviderPrice("AAPL", observed, Decimal("30")),)), request(), observed
    )

    conflict = service.ingest(
        FakeProvider((ProviderPrice("AAPL", observed, Decimal("31")),)),
        request(29),
        datetime(2026, 4, 1, tzinfo=UTC),
    )

    assert conflict.conflict_count == 1
    assert conflict.results[0].status is PriceIngestionStatus.CONFLICT
    assert service.latest_quote(
        INSTRUMENT_ID, datetime(2026, 4, 2, tzinfo=UTC), timedelta(days=5)
    ).price == Decimal("30")


def test_cutoff_excludes_future_prices_and_detects_staleness(session) -> None:
    service = MarketDataService(session)
    prices = (
        ProviderPrice("AAPL", datetime(2026, 3, 28, tzinfo=UTC), Decimal("28")),
        ProviderPrice("AAPL", datetime(2026, 4, 1, tzinfo=UTC), Decimal("40")),
    )
    service.ingest(FakeProvider(prices), request(), datetime(2026, 4, 2, tzinfo=UTC))

    quote = service.latest_quote(
        INSTRUMENT_ID, datetime(2026, 3, 31, tzinfo=UTC), timedelta(days=1)
    )
    assert quote.price == Decimal("28")
    assert quote.freshness is FreshnessStatus.STALE
    with pytest.raises(MissingPriceError):
        service.latest_quote(INSTRUMENT_ID, datetime(2026, 3, 1, tzinfo=UTC), timedelta(days=1))


def test_invalid_price_and_naive_time_are_rejected(session) -> None:
    service = MarketDataService(session)
    with pytest.raises(InvalidPriceObservation):
        service.ingest(
            FakeProvider((ProviderPrice("AAPL", datetime(2026, 3, 31, tzinfo=UTC), Decimal("0")),)),
            request(),
            datetime(2026, 4, 1, tzinfo=UTC),
        )
