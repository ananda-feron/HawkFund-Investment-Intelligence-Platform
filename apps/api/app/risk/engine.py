from collections.abc import Iterable
from decimal import ROUND_CEILING, Decimal

from app.analytics.engine import annualized_stddev, beta
from app.exposures.types import ExposureResult
from app.risk.errors import RiskError
from app.risk.types import RiskResult

ZERO = Decimal("0")


class RiskEngine:
    def calculate(
        self,
        portfolio_returns: Iterable[Decimal],
        benchmark_returns: Iterable[Decimal],
        portfolio_value: Decimal,
        exposure: ExposureResult,
        confidence_level: Decimal = Decimal("0.95"),
        annualization_periods: int = 252,
    ) -> RiskResult:
        returns = tuple(portfolio_returns)
        benchmark = tuple(benchmark_returns)
        if not returns:
            raise RiskError("at least one portfolio return is required")
        if portfolio_value <= ZERO:
            raise RiskError("portfolio value must be positive")
        if not ZERO < confidence_level < Decimal("1"):
            raise RiskError("confidence level must be between zero and one")
        if benchmark and len(benchmark) != len(returns):
            raise RiskError("benchmark and portfolio returns must be aligned")
        losses = sorted(-item for item in returns)
        rank = int(
            (confidence_level * Decimal(len(losses))).to_integral_value(rounding=ROUND_CEILING)
        )
        var_return = max(ZERO, losses[max(0, rank - 1)])
        tail = tuple(item for item in losses if item >= var_return)
        expected_shortfall = max(ZERO, sum(tail, ZERO) / Decimal(len(tail)))
        tracking = None
        portfolio_beta = None
        if benchmark:
            active = tuple(p - b for p, b in zip(returns, benchmark, strict=True))
            tracking = annualized_stddev(active, annualization_periods)
            portfolio_beta = beta(returns, benchmark)
        return RiskResult(
            len(returns),
            confidence_level,
            annualized_stddev(returns, annualization_periods),
            portfolio_beta,
            var_return,
            expected_shortfall,
            portfolio_value * var_return,
            portfolio_value * expected_shortfall,
            tracking,
            exposure.largest_position_weight,
            exposure.herfindahl_index,
        )
