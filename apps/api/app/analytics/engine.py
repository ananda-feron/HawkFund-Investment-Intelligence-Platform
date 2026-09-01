from collections.abc import Iterable
from decimal import Decimal

from app.analytics.errors import AnalyticsError
from app.analytics.types import (
    AnalyticsResult,
    AttributionInput,
    AttributionResult,
    BenchmarkComparison,
    DrawdownObservation,
    ReturnObservation,
    ValueObservation,
)

ZERO = Decimal("0")
ONE = Decimal("1")


class AnalyticsEngine:
    def analyze(
        self,
        observations: Iterable[ValueObservation],
        annualization_periods: int = 252,
        annual_risk_free_rate: Decimal = ZERO,
    ) -> AnalyticsResult:
        ordered = self._values(observations)
        returns: list[ReturnObservation] = []
        growth = ONE
        peak_growth = ONE
        drawdowns: list[DrawdownObservation] = [DrawdownObservation(ordered[0].observed_at, ZERO)]
        for index, item in enumerate(ordered):
            if index == 0:
                continue
            previous = ordered[index - 1]
            period_return = (item.value - item.external_flow) / previous.value - ONE
            growth *= ONE + period_return
            if growth > peak_growth:
                peak_growth = growth
            returns.append(ReturnObservation(item.observed_at, period_return, growth - ONE))
            drawdowns.append(DrawdownObservation(item.observed_at, growth / peak_growth - ONE))
        series = tuple(item.period_return for item in returns)
        period_stddev = sample_stddev(series)
        volatility = (
            None if period_stddev is None else period_stddev * Decimal(annualization_periods).sqrt()
        )
        sharpe = None
        if period_stddev is not None and period_stddev != ZERO:
            period_rf = annual_risk_free_rate / Decimal(annualization_periods)
            sharpe = (
                (mean(series) - period_rf) * Decimal(annualization_periods).sqrt() / period_stddev
            )
        return AnalyticsResult(
            tuple(returns),
            tuple(drawdowns),
            growth - ONE,
            volatility,
            sharpe,
            min((item.drawdown for item in drawdowns), default=ZERO),
        )

    def compare(
        self,
        portfolio_returns: Iterable[ReturnObservation],
        benchmark_returns: Iterable[ReturnObservation],
        annualization_periods: int = 252,
    ) -> BenchmarkComparison:
        portfolio = {item.observed_at: item.period_return for item in portfolio_returns}
        benchmark = {item.observed_at: item.period_return for item in benchmark_returns}
        timestamps = sorted(portfolio.keys() & benchmark.keys())
        if not timestamps:
            raise AnalyticsError("portfolio and benchmark have no aligned return observations")
        p = tuple(portfolio[item] for item in timestamps)
        b = tuple(benchmark[item] for item in timestamps)
        p_total = compound(p)
        b_total = compound(b)
        return BenchmarkComparison(
            len(timestamps),
            p_total,
            b_total,
            p_total - b_total,
            annualized_stddev(
                tuple(x - y for x, y in zip(p, b, strict=True)), annualization_periods
            ),
            beta(p, b),
        )

    def attribute(self, inputs: Iterable[AttributionInput]) -> tuple[AttributionResult, ...]:
        rows = tuple(inputs)
        if any(item.beginning_weight < ZERO for item in rows):
            raise AnalyticsError("attribution weights cannot be negative")
        if sum((item.beginning_weight for item in rows), ZERO) > ONE:
            raise AnalyticsError("attribution weights cannot exceed total portfolio weight")
        return tuple(
            AttributionResult(item.instrument_id, item.beginning_weight * item.security_return)
            for item in sorted(rows, key=lambda row: str(row.instrument_id))
        )

    @staticmethod
    def _values(observations: Iterable[ValueObservation]) -> tuple[ValueObservation, ...]:
        ordered = tuple(sorted(observations, key=lambda item: item.observed_at))
        if not ordered:
            raise AnalyticsError("at least one value observation is required")
        if len({item.observed_at for item in ordered}) != len(ordered):
            raise AnalyticsError("value timestamps must be unique")
        for item in ordered:
            if item.observed_at.tzinfo is None:
                raise AnalyticsError("value timestamps must be timezone-aware")
            if item.value <= ZERO:
                raise AnalyticsError("portfolio values must be positive")
        return ordered


def mean(values: tuple[Decimal, ...]) -> Decimal:
    if not values:
        raise AnalyticsError("at least one return is required")
    return sum(values, ZERO) / Decimal(len(values))


def sample_stddev(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    average = mean(values)
    variance = sum(((item - average) ** 2 for item in values), ZERO) / Decimal(len(values) - 1)
    return variance.sqrt()


def annualized_stddev(values: tuple[Decimal, ...], periods: int) -> Decimal | None:
    if periods <= 0:
        raise AnalyticsError("annualization periods must be positive")
    result = sample_stddev(values)
    return None if result is None else result * Decimal(periods).sqrt()


def compound(values: tuple[Decimal, ...]) -> Decimal:
    growth = ONE
    for item in values:
        growth *= ONE + item
    return growth - ONE


def beta(portfolio: tuple[Decimal, ...], benchmark: tuple[Decimal, ...]) -> Decimal | None:
    if len(portfolio) != len(benchmark) or len(portfolio) < 2:
        return None
    p_mean = mean(portfolio)
    b_mean = mean(benchmark)
    denominator = sum(((item - b_mean) ** 2 for item in benchmark), ZERO)
    if denominator == ZERO:
        return None
    numerator = sum(
        ((p - p_mean) * (b - b_mean) for p, b in zip(portfolio, benchmark, strict=True)), ZERO
    )
    return numerator / denominator
