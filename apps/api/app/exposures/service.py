from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.exposures.engine import ExposureEngine
from app.exposures.types import (
    ExposureResult,
    InstrumentClassification,
    PositionExposureInput,
)
from app.models import InstrumentClassificationRecord
from app.valuation.types import ValuationResult


class ExposureService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def calculate(self, valuation: ValuationResult, top_n: int = 10) -> ExposureResult:
        instrument_ids = {item.instrument_id for item in valuation.positions}
        classifications = self.classifications_at(instrument_ids, valuation.as_of)
        positions = tuple(
            PositionExposureInput(item.instrument_id, item.market_value)
            for item in valuation.positions
        )
        return ExposureEngine().calculate(
            positions, valuation.cash_value, classifications, top_n=top_n
        )

    def classifications_at(
        self, instrument_ids: set[UUID], as_of: datetime
    ) -> dict[UUID, InstrumentClassification]:
        if not instrument_ids:
            return {}
        rows = self.session.scalars(
            select(InstrumentClassificationRecord)
            .where(
                InstrumentClassificationRecord.instrument_id.in_(instrument_ids),
                InstrumentClassificationRecord.effective_from <= as_of,
                or_(
                    InstrumentClassificationRecord.effective_to.is_(None),
                    InstrumentClassificationRecord.effective_to > as_of,
                ),
            )
            .order_by(
                InstrumentClassificationRecord.instrument_id,
                InstrumentClassificationRecord.effective_from.desc(),
            )
        ).all()
        classifications: dict[UUID, InstrumentClassification] = {}
        for row in rows:
            classifications.setdefault(
                row.instrument_id,
                InstrumentClassification(
                    row.instrument_id,
                    row.sector,
                    row.asset_class,
                    row.geography,
                    self._aware(row.effective_from),
                    self._aware(row.effective_to) if row.effective_to else None,
                ),
            )
        return classifications

    @staticmethod
    def _aware(value: datetime) -> datetime:
        from datetime import UTC

        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
