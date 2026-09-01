from typing import Protocol

from app.market_data.types import PriceRequest, ProviderPrice


class MarketDataProvider(Protocol):
    @property
    def name(self) -> str: ...

    def fetch_prices(self, request: PriceRequest) -> tuple[ProviderPrice, ...]: ...
