import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.errors import (
    InvalidPriceObservation,
    MissingPriceError,
    UnknownSecurityIdentifier,
)
from app.market_data.provider import MarketDataProvider
from app.market_data.types import (
    BatchIngestionResult,
    FreshnessStatus,
    IdentifierScheme,
    MarketDataBatchStatus,
    PriceIngestionResult,
    PriceIngestionStatus,
    PriceQuote,
    PriceRequest,
    PriceType,
    ProviderPrice,
)
from app.models import (
    MarketDataBatch,
    MarketPrice,
    MarketPriceConflict,
    SecurityIdentifier,
)


class MarketDataService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def ingest(
        self, provider: MarketDataProvider, request: PriceRequest, received_at: datetime
    ) -> BatchIngestionResult:
        self._aware(received_at, "received_at")
        self._aware(request.start, "request.start")
        self._aware(request.end, "request.end")
        if request.end < request.start:
            raise InvalidPriceObservation("request end precedes start")
        request_hash = self._request_hash(provider.name, request)
        existing_batch = self.session.scalar(
            select(MarketDataBatch).where(
                MarketDataBatch.provider == provider.name,
                MarketDataBatch.dataset == request.price_type.value,
                MarketDataBatch.request_hash == request_hash,
            )
        )
        if existing_batch is not None:
            return self._batch_result(existing_batch)

        batch = MarketDataBatch(
            id=uuid4(),
            provider=provider.name,
            dataset=request.price_type.value,
            request_hash=request_hash,
            status=MarketDataBatchStatus.RECEIVED,
            started_at=received_at,
            completed_at=None,
            inserted_count=0,
            duplicate_count=0,
            conflict_count=0,
        )
        self.session.add(batch)
        self.session.flush()
        results = tuple(
            self._ingest_one(batch, provider.name, item, received_at)
            for item in provider.fetch_prices(request)
        )
        batch.inserted_count = sum(item.status is PriceIngestionStatus.INSERTED for item in results)
        batch.duplicate_count = sum(
            item.status is PriceIngestionStatus.DUPLICATE for item in results
        )
        batch.conflict_count = sum(item.status is PriceIngestionStatus.CONFLICT for item in results)
        batch.status = (
            MarketDataBatchStatus.COMPLETED_WITH_CONFLICTS
            if batch.conflict_count
            else MarketDataBatchStatus.COMPLETED
        )
        batch.completed_at = received_at
        self.session.commit()
        return BatchIngestionResult(
            batch.id, batch.inserted_count, batch.duplicate_count, batch.conflict_count, results
        )

    def latest_quote(
        self,
        instrument_id: UUID,
        as_of: datetime,
        max_age: timedelta,
        provider: str | None = None,
        price_type: PriceType = PriceType.CLOSE,
    ) -> PriceQuote:
        self._aware(as_of, "as_of")
        if max_age < timedelta(0):
            raise InvalidPriceObservation("max_age cannot be negative")
        query = select(MarketPrice).where(
            MarketPrice.instrument_id == instrument_id,
            MarketPrice.price_type == price_type,
            MarketPrice.observed_at <= as_of,
        )
        if provider is not None:
            query = query.where(MarketPrice.provider == provider)
        row = self.session.scalar(
            query.order_by(
                MarketPrice.observed_at.desc(), MarketPrice.provider, MarketPrice.id
            ).limit(1)
        )
        if row is None:
            raise MissingPriceError(
                f"no {price_type.value} price at or before {as_of.isoformat()} for {instrument_id}"
            )
        observed_at = self._utc(row.observed_at)
        age = as_of.astimezone(UTC) - observed_at
        freshness = FreshnessStatus.STALE if age > max_age else FreshnessStatus.FRESH
        return PriceQuote(
            row.id,
            row.instrument_id,
            row.provider,
            row.price_type,
            observed_at,
            self._utc(row.received_at),
            row.price,
            row.currency,
            row.source_identifier,
            freshness,
            Decimal(str(age.total_seconds())),
            row.source_metadata,
        )

    def _ingest_one(
        self, batch: MarketDataBatch, provider: str, item: ProviderPrice, received_at: datetime
    ) -> PriceIngestionResult:
        self._validate(item)
        instrument_id = self._resolve(provider, item.identifier, item.observed_at)
        observed_at = item.observed_at.astimezone(UTC)
        existing = self.session.scalar(
            select(MarketPrice).where(
                MarketPrice.instrument_id == instrument_id,
                MarketPrice.provider == provider,
                MarketPrice.price_type == item.price_type,
                MarketPrice.observed_at == observed_at,
            )
        )
        if existing is not None:
            if existing.price == item.price and existing.currency == item.currency:
                return PriceIngestionResult(
                    item.identifier, PriceIngestionStatus.DUPLICATE, existing.id, None
                )
            conflict = MarketPriceConflict(
                id=uuid4(),
                batch_id=batch.id,
                existing_price_id=existing.id,
                incoming_price=item.price,
                incoming_currency=item.currency,
                incoming_metadata=item.source_metadata or {},
                detected_at=received_at,
            )
            self.session.add(conflict)
            self.session.flush()
            return PriceIngestionResult(
                item.identifier, PriceIngestionStatus.CONFLICT, existing.id, conflict.id
            )
        price = MarketPrice(
            id=uuid4(),
            instrument_id=instrument_id,
            batch_id=batch.id,
            provider=provider,
            price_type=item.price_type,
            observed_at=observed_at,
            received_at=received_at,
            price=item.price,
            currency=item.currency,
            source_identifier=item.identifier,
            source_metadata=item.source_metadata or {},
        )
        self.session.add(price)
        self.session.flush()
        return PriceIngestionResult(item.identifier, PriceIngestionStatus.INSERTED, price.id, None)

    def _resolve(self, provider: str, value: str, observed_at: datetime) -> UUID:
        candidates = self.session.scalars(
            select(SecurityIdentifier)
            .where(
                SecurityIdentifier.value == value,
                SecurityIdentifier.provider.in_((provider, "")),
                SecurityIdentifier.scheme.in_((IdentifierScheme.PROVIDER, IdentifierScheme.TICKER)),
            )
            .order_by(SecurityIdentifier.provider.desc(), SecurityIdentifier.is_primary.desc())
        ).all()
        instant = observed_at.astimezone(UTC)
        for item in candidates:
            valid_from = self._utc(item.valid_from) if item.valid_from else None
            valid_to = self._utc(item.valid_to) if item.valid_to else None
            if (valid_from is None or valid_from <= instant) and (
                valid_to is None or instant < valid_to
            ):
                return item.instrument_id
        raise UnknownSecurityIdentifier(f"unmapped identifier {provider}:{value}")

    @staticmethod
    def _validate(item: ProviderPrice) -> None:
        MarketDataService._aware(item.observed_at, "observed_at")
        if item.price <= 0:
            raise InvalidPriceObservation("price must be positive")
        if item.currency != "USD":
            raise InvalidPriceObservation("Phase 2 valuation supports USD prices only")
        if not item.identifier.strip():
            raise InvalidPriceObservation("identifier is required")

    @staticmethod
    def _request_hash(provider: str, request: PriceRequest) -> str:
        payload = {
            "provider": provider,
            "identifiers": sorted(request.identifiers),
            "start": request.start.astimezone(UTC).isoformat(),
            "end": request.end.astimezone(UTC).isoformat(),
            "price_type": request.price_type.value,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _batch_result(self, batch: MarketDataBatch) -> BatchIngestionResult:
        rows = self.session.scalars(
            select(MarketPrice).where(MarketPrice.batch_id == batch.id)
        ).all()
        results = tuple(
            PriceIngestionResult(row.source_identifier, PriceIngestionStatus.INSERTED, row.id, None)
            for row in rows
        )
        return BatchIngestionResult(
            batch.id, batch.inserted_count, batch.duplicate_count, batch.conflict_count, results
        )

    @staticmethod
    def _aware(value: datetime, name: str) -> None:
        if value.tzinfo is None:
            raise InvalidPriceObservation(f"{name} must be timezone-aware")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
