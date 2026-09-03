from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.models import (
    InstrumentClassificationRecord,
    RiskPolicy,
    RiskPolicyRule,
    ScenarioDefinitionRecord,
    ScenarioPositionResultRecord,
    ScenarioRun,
    ScenarioShockRecord,
)
from app.risk.policy import PolicyEvaluationStatus, PolicyOperator
from app.scenarios.service import ScenarioService
from app.scenarios.types import ScenarioKind, ShockTargetType, ShockUnit
from tests.conftest import FUND_ID, INSTRUMENT_ID
from tests.scenarios.factories import AS_OF, valuation


def test_execution_persists_idempotent_scenario_and_position_evidence(session) -> None:
    policy_id = UUID(int=501)
    rule_id = UUID(int=502)
    scenario_id = UUID(int=503)
    session.add_all(
        [
            InstrumentClassificationRecord(
                id=UUID(int=504),
                instrument_id=INSTRUMENT_ID,
                sector="Technology",
                asset_class="Equity",
                geography="US",
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=None,
                source="test",
                source_metadata={},
                recorded_at=AS_OF,
            ),
            RiskPolicy(
                id=policy_id,
                fund_id=FUND_ID,
                name="Scenario Policy",
                version=1,
                effective_from=datetime(2026, 1, 1, tzinfo=UTC),
                effective_to=None,
                created_at=AS_OF,
                created_by_user_id=None,
            ),
            ScenarioDefinitionRecord(
                id=scenario_id,
                fund_id=FUND_ID,
                name="AAPL rally",
                version=1,
                kind=ScenarioKind.HYPOTHETICAL,
                description="test",
                source_metadata={},
                created_at=AS_OF,
                created_by_user_id=None,
            ),
        ]
    )
    session.flush()
    session.add_all(
        [
            RiskPolicyRule(
                id=rule_id,
                policy_id=policy_id,
                metric_key="sector.Technology",
                operator=PolicyOperator.MAX,
                threshold=Decimal("0.55"),
                unit="ratio",
                explanation_template="Technology {observed}; limit {threshold}; breach {breach}",
            ),
            ScenarioShockRecord(
                id=UUID(int=505),
                scenario_id=scenario_id,
                target_type=ShockTargetType.SECURITY,
                target=str(INSTRUMENT_ID),
                magnitude=Decimal("0.5"),
                unit=ShockUnit.RELATIVE_RETURN,
                sequence=1,
            ),
        ]
    )
    session.commit()
    service = ScenarioService(session)
    baseline = valuation(((INSTRUMENT_ID, "500"),), cash="500")
    returns = tuple(Decimal(item) for item in ("0.01", "-0.02", "0.01", "0"))
    benchmark = tuple(Decimal(item) for item in ("0.005", "-0.01", "0.005", "0"))

    first = service.execute(
        scenario_id,
        baseline,
        returns,
        benchmark,
        policy_id,
        AS_OF,
        confidence_level=Decimal("0.8"),
    )
    second = service.execute(
        scenario_id,
        baseline,
        returns,
        benchmark,
        policy_id,
        AS_OF,
        confidence_level=Decimal("0.8"),
    )

    assert first.run_id == second.run_id
    assert first.analysis.scenario.pnl_impact == Decimal("250.0")
    assert first.analysis.projected_policy[0].status is PolicyEvaluationStatus.BREACH
    assert session.scalar(select(func.count()).select_from(ScenarioRun)) == 1
    assert session.scalar(select(func.count()).select_from(ScenarioPositionResultRecord)) == 1
