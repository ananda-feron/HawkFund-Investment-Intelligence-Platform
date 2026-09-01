from collections import defaultdict
from collections.abc import Iterable, Mapping
from decimal import Decimal
from uuid import UUID

from app.exposures.errors import ExposureError
from app.exposures.types import (
    CategoryExposure,
    ExposureResult,
    InstrumentClassification,
    PositionExposureInput,
    PositionWeight,
)

ZERO = Decimal("0")


class ExposureEngine:
    def calculate(
        self,
        positions: Iterable[PositionExposureInput],
        cash_value: Decimal,
        classifications: Mapping[UUID, InstrumentClassification],
        top_n: int = 10,
    ) -> ExposureResult:
        rows = tuple(positions)
        if cash_value < ZERO or any(item.market_value < ZERO for item in rows):
            raise ExposureError("Phase 3 exposure supports long-only, nonnegative values")
        if top_n <= 0:
            raise ExposureError("top_n must be positive")
        total = cash_value + sum((item.market_value for item in rows), ZERO)
        if total <= ZERO:
            raise ExposureError("portfolio value must be positive")
        weights = tuple(
            sorted(
                (
                    PositionWeight(item.instrument_id, item.market_value, item.market_value / total)
                    for item in rows
                ),
                key=lambda item: (-item.weight, str(item.instrument_id)),
            )
        )
        warnings: list[str] = []
        sector: dict[str, Decimal] = defaultdict(lambda: ZERO)
        asset: dict[str, Decimal] = defaultdict(lambda: ZERO)
        geography: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for item in rows:
            classification = classifications.get(item.instrument_id)
            if classification is None:
                warnings.append(f"missing classification for {item.instrument_id}")
                labels = ("UNCLASSIFIED", "UNCLASSIFIED", "UNCLASSIFIED")
            else:
                labels = (
                    classification.sector,
                    classification.asset_class,
                    classification.geography,
                )
            sector[labels[0]] += item.market_value
            asset[labels[1]] += item.market_value
            geography[labels[2]] += item.market_value
        if cash_value:
            sector["CASH"] += cash_value
            asset["CASH"] += cash_value
            geography["CASH"] += cash_value
        return ExposureResult(
            total,
            cash_value,
            weights,
            self._categories(sector, total),
            self._categories(asset, total),
            self._categories(geography, total),
            weights[:top_n],
            weights[0].weight if weights else ZERO,
            sum((item.weight**2 for item in weights), ZERO),
            tuple(warnings),
        )

    @staticmethod
    def _categories(values: Mapping[str, Decimal], total: Decimal) -> tuple[CategoryExposure, ...]:
        return tuple(
            CategoryExposure(category, value, value / total)
            for category, value in sorted(values.items(), key=lambda item: (-item[1], item[0]))
        )
