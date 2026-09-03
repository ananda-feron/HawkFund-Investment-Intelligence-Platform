from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from uuid import UUID

from app.exposures.types import ExposureResult
from app.risk.types import RiskResult


class PolicyOperator(str, Enum):
    MAX = "MAX"
    MIN = "MIN"


class PolicyEvaluationStatus(str, Enum):
    PASS = "PASS"
    BREACH = "BREACH"
    UNAVAILABLE = "UNAVAILABLE"


class PolicyRuleSeverity(str, Enum):
    BLOCKING = "BLOCKING"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class PolicyRuleInput:
    rule_id: UUID
    metric_key: str
    operator: PolicyOperator
    threshold: Decimal
    unit: str
    explanation_template: str


@dataclass(frozen=True, slots=True)
class PolicyEvaluationItem:
    rule_id: UUID
    metric_key: str
    status: PolicyEvaluationStatus
    observed_value: Decimal | None
    threshold: Decimal
    breach_amount: Decimal | None
    unit: str
    explanation: str


class PolicyEngine:
    def evaluate(
        self,
        rules: Iterable[PolicyRuleInput],
        metrics: Mapping[str, Decimal],
    ) -> tuple[PolicyEvaluationItem, ...]:
        output: list[PolicyEvaluationItem] = []
        for rule in sorted(rules, key=lambda item: str(item.rule_id)):
            observed = metrics.get(rule.metric_key)
            if observed is None:
                output.append(
                    PolicyEvaluationItem(
                        rule.rule_id,
                        rule.metric_key,
                        PolicyEvaluationStatus.UNAVAILABLE,
                        None,
                        rule.threshold,
                        None,
                        rule.unit,
                        f"{rule.metric_key} is unavailable; threshold {rule.threshold} {rule.unit}",
                    )
                )
                continue
            if rule.operator is PolicyOperator.MAX:
                amount = observed - rule.threshold
            else:
                amount = rule.threshold - observed
            breached = amount > Decimal("0")
            status = PolicyEvaluationStatus.BREACH if breached else PolicyEvaluationStatus.PASS
            explanation = rule.explanation_template.format(
                metric=rule.metric_key,
                observed=observed,
                threshold=rule.threshold,
                breach=max(amount, Decimal("0")),
                unit=rule.unit,
            )
            output.append(
                PolicyEvaluationItem(
                    rule.rule_id,
                    rule.metric_key,
                    status,
                    observed,
                    rule.threshold,
                    max(amount, Decimal("0")) if breached else Decimal("0"),
                    rule.unit,
                    explanation,
                )
            )
        return tuple(output)


def exposure_metrics(
    sector: Mapping[str, Decimal],
    asset_class: Mapping[str, Decimal],
    geography: Mapping[str, Decimal],
    largest_position_weight: Decimal,
    herfindahl_index: Decimal,
) -> dict[str, Decimal]:
    metrics = {
        "concentration.largest_position_weight": largest_position_weight,
        "concentration.herfindahl_index": herfindahl_index,
    }
    metrics.update({f"sector.{key}": value for key, value in sector.items()})
    metrics.update({f"asset_class.{key}": value for key, value in asset_class.items()})
    metrics.update({f"geography.{key}": value for key, value in geography.items()})
    return metrics


def portfolio_risk_metrics(exposure: ExposureResult, risk: RiskResult) -> dict[str, Decimal]:
    metrics = exposure_metrics(
        {item.category: item.weight for item in exposure.sector_exposure},
        {item.category: item.weight for item in exposure.asset_allocation},
        {item.category: item.weight for item in exposure.geographic_exposure},
        exposure.largest_position_weight,
        exposure.herfindahl_index,
    )
    optional = {
        "risk.volatility": risk.annualized_volatility,
        "risk.beta": risk.beta,
        "risk.tracking_error": risk.tracking_error,
    }
    metrics.update({key: value for key, value in optional.items() if value is not None})
    metrics.update(
        {
            "risk.var_return": risk.value_at_risk_return,
            "risk.expected_shortfall_return": risk.expected_shortfall_return,
        }
    )
    return metrics
