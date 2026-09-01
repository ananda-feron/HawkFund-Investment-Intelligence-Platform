from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.models import RiskEvaluation, RiskEvaluationItem, RiskPolicy, RiskPolicyRule
from app.risk.policy import (
    PolicyEngine,
    PolicyEvaluationStatus,
    PolicyOperator,
    PolicyRuleInput,
)
from app.risk.service import RiskPolicyService
from tests.conftest import FUND_ID


def rule(number: int, metric: str, threshold: str) -> PolicyRuleInput:
    return PolicyRuleInput(
        UUID(int=number),
        metric,
        PolicyOperator.MAX,
        Decimal(threshold),
        "ratio",
        "{metric}: {observed}; limit: {threshold}; breach: {breach} {unit}",
    )


def test_policy_breach_is_quantified_and_explained() -> None:
    results = PolicyEngine().evaluate(
        (rule(1, "sector.Technology", "0.35"), rule(2, "risk.beta", "1.20")),
        {"sector.Technology": Decimal("0.384")},
    )

    assert results[0].status is PolicyEvaluationStatus.BREACH
    assert results[0].breach_amount == Decimal("0.034")
    assert "0.384" in results[0].explanation
    assert results[1].status is PolicyEvaluationStatus.UNAVAILABLE
    assert results[1].observed_value is None


def test_threshold_boundary_passes() -> None:
    result = PolicyEngine().evaluate(
        (rule(1, "sector.Technology", "0.35"),),
        {"sector.Technology": Decimal("0.35")},
    )[0]
    assert result.status is PolicyEvaluationStatus.PASS
    assert result.breach_amount == Decimal("0")


def test_versioned_policy_evaluation_is_persisted_idempotently(session) -> None:
    policy_id = UUID(int=100)
    rule_id = UUID(int=101)
    as_of = datetime(2026, 3, 31, tzinfo=UTC)
    session.add(
        RiskPolicy(
            id=policy_id,
            fund_id=FUND_ID,
            name="Investment Policy",
            version=1,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_by_user_id=None,
        )
    )
    session.flush()
    session.add(
        RiskPolicyRule(
            id=rule_id,
            policy_id=policy_id,
            metric_key="sector.Technology",
            operator=PolicyOperator.MAX,
            threshold=Decimal("0.35"),
            unit="ratio",
            explanation_template="Technology {observed}; limit {threshold}; breach {breach}",
        )
    )
    session.commit()
    service = RiskPolicyService(session)

    first = service.evaluate_and_record(
        FUND_ID, policy_id, as_of, {"sector.Technology": Decimal("0.384")}, as_of
    )
    second = service.evaluate_and_record(
        FUND_ID, policy_id, as_of, {"sector.Technology": Decimal("0.384")}, as_of
    )

    assert first[0] == second[0]
    assert first[1][0].status is PolicyEvaluationStatus.BREACH
    assert session.scalar(select(func.count()).select_from(RiskEvaluation)) == 1
    assert session.scalar(select(func.count()).select_from(RiskEvaluationItem)) == 1
