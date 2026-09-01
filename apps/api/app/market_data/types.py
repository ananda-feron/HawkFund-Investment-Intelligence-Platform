from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


class IdentifierScheme(str, Enum):
    TICKER = "TICKER"
    FIGI = "FIGI"
    CUSIP = "CUSIP"
    ISIN = "ISIN"
    PROVIDER = "PROVIDER"


class PriceType(str, Enum):
    CLOSE = "CLOSE"
    ADJUSTED_CLOSE = "ADJUSTED_CLOSE"


class MarketDataBatchStatus(str, Enum):
    RECEIVED = "RECEIVED"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_CONFLICTS = "COMPLETED_WITH_CONFLICTS"
    FAILED = "FAILED"


class PriceIngestionStatus(str, Enum):
    INSERTED = "INSERTED"
    DUPLICATE = "DUPLICATE"
    CONFLICT = "CONFLICT"


class FreshnessStatus(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class PriceRequest:
    identifiers: tuple[str, ...]
    start: datetime
    end: datetime
    price_type: PriceType = PriceType.CLOSE


@dataclass(frozen=True, slots=True)
class ProviderPrice:
    identifier: str
    observed_at: datetime
    price: Decimal
    currency: str = "USD"
    price_type: PriceType = PriceType.CLOSE
    source_metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PriceQuote:
    observation_id: UUID
    instrument_id: UUID
    provider: str
    price_type: PriceType
    observed_at: datetime
    received_at: datetime
    price: Decimal
    currency: str
    source_identifier: str
    freshness: FreshnessStatus
    age_seconds: Decimal
    source_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class PriceIngestionResult:
    identifier: str
    status: PriceIngestionStatus
    observation_id: UUID | None
    conflict_id: UUID | None


@dataclass(frozen=True, slots=True)
class BatchIngestionResult:
    batch_id: UUID
    inserted_count: int
    duplicate_count: int
    conflict_count: int
    results: tuple[PriceIngestionResult, ...]
