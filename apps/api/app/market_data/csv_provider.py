import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import StringIO

from app.market_data.errors import InvalidPriceObservation
from app.market_data.types import PriceRequest, PriceType, ProviderPrice


class CsvMarketDataProvider:
    """Deterministic adapter for normalized provider exports.

    Required headers: identifier, observed_at, price. Optional: currency, price_type.
    """

    def __init__(self, content: str, provider_name: str = "csv") -> None:
        self.content = content
        self._name = provider_name

    @property
    def name(self) -> str:
        return self._name

    def fetch_prices(self, request: PriceRequest) -> tuple[ProviderPrice, ...]:
        reader = csv.DictReader(StringIO(self.content))
        required = {"identifier", "observed_at", "price"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise InvalidPriceObservation("CSV requires identifier, observed_at, and price headers")
        output: list[ProviderPrice] = []
        requested = set(request.identifiers)
        for row_number, row in enumerate(reader, start=2):
            try:
                identifier = row["identifier"].strip()
                observed_at = datetime.fromisoformat(row["observed_at"].replace("Z", "+00:00"))
                if observed_at.tzinfo is None:
                    raise ValueError("observed_at must include a timezone")
                price = Decimal(row["price"])
                price_type = PriceType(row.get("price_type") or request.price_type.value)
            except (AttributeError, InvalidOperation, KeyError, ValueError) as error:
                raise InvalidPriceObservation(f"invalid CSV row {row_number}: {error}") from error
            if identifier not in requested or not (request.start <= observed_at <= request.end):
                continue
            output.append(
                ProviderPrice(
                    identifier=identifier,
                    observed_at=observed_at,
                    price=price,
                    currency=row.get("currency") or "USD",
                    price_type=price_type,
                    source_metadata={"row_number": row_number},
                )
            )
        return tuple(output)
