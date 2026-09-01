from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class InstrumentClassification:
    instrument_id: UUID
    sector: str
    asset_class: str
    geography: str
    effective_from: datetime | None = None
    effective_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class PositionExposureInput:
    instrument_id: UUID
    market_value: Decimal


@dataclass(frozen=True, slots=True)
class PositionWeight:
    instrument_id: UUID
    market_value: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class CategoryExposure:
    category: str
    market_value: Decimal
    weight: Decimal


@dataclass(frozen=True, slots=True)
class ExposureResult:
    portfolio_value: Decimal
    cash_value: Decimal
    position_weights: tuple[PositionWeight, ...]
    sector_exposure: tuple[CategoryExposure, ...]
    asset_allocation: tuple[CategoryExposure, ...]
    geographic_exposure: tuple[CategoryExposure, ...]
    top_holdings: tuple[PositionWeight, ...]
    largest_position_weight: Decimal
    herfindahl_index: Decimal
    warnings: tuple[str, ...]
