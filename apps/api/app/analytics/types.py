from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ValueObservation:
    observed_at: datetime
    value: Decimal
    external_flow: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class ReturnObservation:
    observed_at: datetime
    period_return: Decimal
    cumulative_return: Decimal


@dataclass(frozen=True, slots=True)
class DrawdownObservation:
    observed_at: datetime
    drawdown: Decimal


@dataclass(frozen=True, slots=True)
class AttributionInput:
    instrument_id: UUID
    beginning_weight: Decimal
    security_return: Decimal


@dataclass(frozen=True, slots=True)
class AttributionResult:
    instrument_id: UUID
    contribution: Decimal


@dataclass(frozen=True, slots=True)
class AnalyticsResult:
    returns: tuple[ReturnObservation, ...]
    drawdowns: tuple[DrawdownObservation, ...]
    total_return: Decimal
    annualized_volatility: Decimal | None
    annualized_sharpe: Decimal | None
    maximum_drawdown: Decimal


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    aligned_count: int
    portfolio_total_return: Decimal
    benchmark_total_return: Decimal
    excess_total_return: Decimal
    tracking_error: Decimal | None
    beta: Decimal | None
