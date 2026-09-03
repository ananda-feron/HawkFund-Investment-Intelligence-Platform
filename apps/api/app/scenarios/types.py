from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from app.exposures.types import ExposureResult, InstrumentClassification
from app.risk.policy import PolicyEvaluationItem
from app.risk.types import RiskResult
from app.valuation.types import ValuationResult


class ScenarioKind(str, Enum):
    HYPOTHETICAL = "HYPOTHETICAL"
    HISTORICAL = "HISTORICAL"


class ShockTargetType(str, Enum):
    SECURITY = "SECURITY"
    MARKET = "MARKET"
    SECTOR = "SECTOR"
    RATE = "RATE"
    FACTOR = "FACTOR"


class ShockUnit(str, Enum):
    RELATIVE_RETURN = "RELATIVE_RETURN"
    YIELD_CHANGE = "YIELD_CHANGE"
    FACTOR_MOVE = "FACTOR_MOVE"


@dataclass(frozen=True, slots=True)
class ScenarioShock:
    id: UUID
    target_type: ShockTargetType
    target: str
    magnitude: Decimal
    unit: ShockUnit
    sequence: int


@dataclass(frozen=True, slots=True)
class ScenarioDefinition:
    id: UUID
    fund_id: UUID
    name: str
    version: int
    kind: ScenarioKind
    shocks: tuple[ScenarioShock, ...]
    source_metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class InstrumentSensitivity:
    instrument_id: UUID
    rate_duration: Decimal | None = None
    factor_loadings: tuple[tuple[str, Decimal], ...] = ()

    def factor_loading(self, factor: str) -> Decimal | None:
        return dict(self.factor_loadings).get(factor)


@dataclass(frozen=True, slots=True)
class ShockContribution:
    shock_id: UUID
    target_type: ShockTargetType
    target: str
    return_impact: Decimal


@dataclass(frozen=True, slots=True)
class ScenarioPositionResult:
    instrument_id: UUID
    baseline_price: Decimal
    projected_price: Decimal
    baseline_market_value: Decimal
    projected_market_value: Decimal
    return_impact: Decimal
    pnl_impact: Decimal
    contributions: tuple[ShockContribution, ...]


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    definition: ScenarioDefinition
    as_of: datetime
    baseline: ValuationResult
    projected: ValuationResult
    positions: tuple[ScenarioPositionResult, ...]
    pnl_impact: Decimal
    portfolio_return_impact: Decimal
    warnings: tuple[str, ...]
    canonical_input_hash: str
    classifications: dict[UUID, InstrumentClassification]


@dataclass(frozen=True, slots=True)
class ExposureChange:
    dimension: str
    category: str
    before_weight: Decimal
    after_weight: Decimal
    change: Decimal


@dataclass(frozen=True, slots=True)
class RiskChange:
    metric: str
    before_value: Decimal | None
    after_value: Decimal | None
    change: Decimal | None


@dataclass(frozen=True, slots=True)
class BeforeAfterResult:
    scenario: ScenarioResult
    baseline_exposure: ExposureResult
    projected_exposure: ExposureResult
    exposure_changes: tuple[ExposureChange, ...]
    baseline_risk: RiskResult
    projected_risk: RiskResult
    risk_changes: tuple[RiskChange, ...]
    baseline_policy: tuple[PolicyEvaluationItem, ...]
    projected_policy: tuple[PolicyEvaluationItem, ...]
