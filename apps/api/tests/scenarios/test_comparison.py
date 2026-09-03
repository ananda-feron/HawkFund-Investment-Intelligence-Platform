from decimal import Decimal
from uuid import UUID

from app.exposures.types import InstrumentClassification
from app.risk.policy import PolicyEvaluationStatus, PolicyOperator, PolicyRuleInput
from app.scenarios.comparison import BeforeAfterEngine
from app.scenarios.engine import ScenarioEngine
from app.scenarios.types import (
    ScenarioDefinition,
    ScenarioKind,
    ScenarioShock,
    ShockTargetType,
    ShockUnit,
)
from tests.conftest import FUND_ID
from tests.scenarios.factories import valuation

TECH = UUID(int=21)
OTHER = UUID(int=22)


def test_before_after_shows_pnl_exposure_risk_and_new_policy_breach() -> None:
    definition = ScenarioDefinition(
        UUID(int=200),
        FUND_ID,
        "Technology rally",
        1,
        ScenarioKind.HYPOTHETICAL,
        (
            ScenarioShock(
                UUID(int=201),
                ShockTargetType.SECURITY,
                str(TECH),
                Decimal("0.5"),
                ShockUnit.RELATIVE_RETURN,
                1,
            ),
        ),
        {},
    )
    baseline = valuation(((TECH, "400"), (OTHER, "100")), cash="500")
    classifications = {
        TECH: InstrumentClassification(TECH, "Technology", "Equity", "US"),
        OTHER: InstrumentClassification(OTHER, "Industrials", "Equity", "US"),
    }
    scenario = ScenarioEngine().apply(baseline, definition, classifications)
    rule = PolicyRuleInput(
        UUID(int=202),
        "sector.Technology",
        PolicyOperator.MAX,
        Decimal("0.45"),
        "ratio",
        "Technology {observed}; limit {threshold}; breach {breach}",
    )

    result = BeforeAfterEngine().compare(
        scenario,
        classifications,
        tuple(Decimal(item) for item in ("0.01", "-0.02", "0.01", "0.00")),
        tuple(Decimal(item) for item in ("0.005", "-0.01", "0.005", "0.00")),
        (rule,),
        confidence_level=Decimal("0.8"),
    )

    technology = next(
        item
        for item in result.exposure_changes
        if item.dimension == "sector" and item.category == "Technology"
    )
    assert scenario.pnl_impact == Decimal("200.0")
    assert technology.before_weight == Decimal("0.4")
    assert technology.after_weight == Decimal("0.5")
    assert result.baseline_policy[0].status is PolicyEvaluationStatus.PASS
    assert result.projected_policy[0].status is PolicyEvaluationStatus.BREACH
    assert result.projected_policy[0].breach_amount == Decimal("0.05")
    assert any(item.change is not None for item in result.risk_changes)
