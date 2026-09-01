from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.analytics.engine import AnalyticsEngine
from app.analytics.errors import AnalyticsError
from app.analytics.types import AttributionInput, ValueObservation


def values(
    numbers: tuple[str, ...], flows: tuple[str, ...] | None = None
) -> tuple[ValueObservation, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    flows = flows or tuple("0" for _ in numbers)
    return tuple(
        ValueObservation(start + timedelta(days=index), Decimal(value), Decimal(flows[index]))
        for index, value in enumerate(numbers)
    )


def test_cash_flow_adjusted_returns_cumulative_volatility_sharpe_and_drawdown() -> None:
    result = AnalyticsEngine().analyze(
        values(("100", "120", "108", "119"), ("0", "10", "0", "0")),
        annualization_periods=4,
    )

    assert tuple(item.period_return for item in result.returns) == (
        Decimal("0.1"),
        Decimal("-0.1"),
        Decimal("0.101851851851851851851851852"),
    )
    assert result.total_return == pytest.approx(Decimal("0.090833333333333333333333333"))
    assert result.maximum_drawdown == Decimal("-0.1")
    assert result.annualized_volatility is not None
    assert result.annualized_sharpe is not None


def test_benchmark_alignment_beta_tracking_error_and_attribution() -> None:
    engine = AnalyticsEngine()
    portfolio = engine.analyze(values(("100", "110", "99", "108.9"))).returns
    benchmark = engine.analyze(values(("100", "105", "99.75", "104.7375"))).returns

    comparison = engine.compare(portfolio, benchmark, annualization_periods=252)
    attribution = engine.attribute(
        (
            AttributionInput(UUID(int=2), Decimal("0.4"), Decimal("0.1")),
            AttributionInput(UUID(int=1), Decimal("0.6"), Decimal("0.05")),
        )
    )

    assert comparison.aligned_count == 3
    assert comparison.beta == pytest.approx(Decimal("2"))
    assert comparison.tracking_error is not None
    assert sum((item.contribution for item in attribution), Decimal("0")) == Decimal("0.07")
    assert tuple(item.instrument_id for item in attribution) == (UUID(int=1), UUID(int=2))


def test_invalid_series_is_rejected() -> None:
    with pytest.raises(AnalyticsError):
        AnalyticsEngine().analyze(())


def test_external_contribution_does_not_create_drawdown_peak() -> None:
    result = AnalyticsEngine().analyze(
        values(("100", "200", "190"), ("0", "100", "0")), annualization_periods=252
    )
    assert tuple(item.drawdown for item in result.drawdowns) == (
        Decimal("0"),
        Decimal("0"),
        Decimal("-0.05"),
    )
