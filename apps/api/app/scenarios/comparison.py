from collections.abc import Iterable, Mapping
from decimal import Decimal
from uuid import UUID

from app.exposures.engine import ExposureEngine
from app.exposures.types import ExposureResult, InstrumentClassification, PositionExposureInput
from app.risk.engine import RiskEngine
from app.risk.policy import PolicyEngine, PolicyRuleInput, portfolio_risk_metrics
from app.risk.types import RiskResult
from app.scenarios.types import (
    BeforeAfterResult,
    ExposureChange,
    RiskChange,
    ScenarioResult,
)


class BeforeAfterEngine:
    def compare(
        self,
        scenario: ScenarioResult,
        classifications: Mapping[UUID, InstrumentClassification],
        portfolio_returns: Iterable[Decimal],
        benchmark_returns: Iterable[Decimal],
        policy_rules: Iterable[PolicyRuleInput],
        benchmark_scenario_return: Decimal = Decimal("0"),
        confidence_level: Decimal = Decimal("0.95"),
        annualization_periods: int = 252,
        top_n: int = 10,
    ) -> BeforeAfterResult:
        returns = tuple(portfolio_returns)
        benchmark = tuple(benchmark_returns)
        exposure_engine = ExposureEngine()
        baseline_exposure = exposure_engine.calculate(
            (
                PositionExposureInput(item.instrument_id, item.market_value)
                for item in scenario.baseline.positions
            ),
            scenario.baseline.cash_value,
            classifications,
            top_n,
        )
        projected_exposure = exposure_engine.calculate(
            (
                PositionExposureInput(item.instrument_id, item.market_value)
                for item in scenario.projected.positions
            ),
            scenario.projected.cash_value,
            classifications,
            top_n,
        )
        risk_engine = RiskEngine()
        baseline_risk = risk_engine.calculate(
            returns,
            benchmark,
            scenario.baseline.portfolio_value,
            baseline_exposure,
            confidence_level,
            annualization_periods,
        )
        projected_risk = risk_engine.calculate(
            returns + (scenario.portfolio_return_impact,),
            benchmark + (benchmark_scenario_return,),
            scenario.projected.portfolio_value,
            projected_exposure,
            confidence_level,
            annualization_periods,
        )
        rules = tuple(policy_rules)
        policy = PolicyEngine()
        return BeforeAfterResult(
            scenario,
            baseline_exposure,
            projected_exposure,
            self._exposure_changes(baseline_exposure, projected_exposure),
            baseline_risk,
            projected_risk,
            self._risk_changes(baseline_risk, projected_risk),
            policy.evaluate(rules, portfolio_risk_metrics(baseline_exposure, baseline_risk)),
            policy.evaluate(rules, portfolio_risk_metrics(projected_exposure, projected_risk)),
        )

    @staticmethod
    def _exposure_changes(
        before: ExposureResult, after: ExposureResult
    ) -> tuple[ExposureChange, ...]:
        output: list[ExposureChange] = []
        for dimension, before_rows, after_rows in (
            ("sector", before.sector_exposure, after.sector_exposure),
            ("asset_class", before.asset_allocation, after.asset_allocation),
            ("geography", before.geographic_exposure, after.geographic_exposure),
        ):
            first = {item.category: item.weight for item in before_rows}
            second = {item.category: item.weight for item in after_rows}
            for category in sorted(first.keys() | second.keys()):
                before_weight = first.get(category, Decimal("0"))
                after_weight = second.get(category, Decimal("0"))
                output.append(
                    ExposureChange(
                        dimension,
                        category,
                        before_weight,
                        after_weight,
                        after_weight - before_weight,
                    )
                )
        return tuple(output)

    @staticmethod
    def _risk_changes(before: RiskResult, after: RiskResult) -> tuple[RiskChange, ...]:
        values = (
            ("volatility", before.annualized_volatility, after.annualized_volatility),
            ("beta", before.beta, after.beta),
            ("var_return", before.value_at_risk_return, after.value_at_risk_return),
            (
                "expected_shortfall_return",
                before.expected_shortfall_return,
                after.expected_shortfall_return,
            ),
            ("tracking_error", before.tracking_error, after.tracking_error),
            (
                "largest_position_weight",
                before.largest_position_weight,
                after.largest_position_weight,
            ),
            ("herfindahl_index", before.herfindahl_index, after.herfindahl_index),
        )
        return tuple(
            RiskChange(
                name, first, second, None if first is None or second is None else second - first
            )
            for name, first, second in values
        )
