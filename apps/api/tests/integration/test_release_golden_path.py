import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.ai.provider import ModelProvider
from app.ai.service import AIIntelligenceService
from app.ai.sql_tools import SqlReadOnlyPortfolioTools
from app.ai.tools import ToolRegistry
from app.ai.types import ConversationStatus, ModelTurn, ToolCall
from app.analytics.engine import AnalyticsEngine
from app.analytics.types import ValueObservation
from app.exposures.service import ExposureService
from app.governance.authorization import AuthorizationService
from app.governance.service import ProposalService
from app.governance.types import (
    ProposalAction,
    ProposalLineInput,
    ProposalStatus,
    ProposalVersionInput,
    ReviewRecommendation,
)
from app.ledger.types import TransactionType
from app.market_data.service import MarketDataService
from app.market_data.types import PriceRequest, ProviderPrice
from app.models import (
    AIToolCall,
    AuditEvent,
    InstrumentClassificationRecord,
    RiskPolicy,
    RiskPolicyRule,
    ScenarioDefinitionRecord,
    ScenarioRun,
    ScenarioShockRecord,
)
from app.risk.engine import RiskEngine
from app.risk.policy import PolicyEvaluationStatus, PolicyOperator, PolicyRuleSeverity
from app.risk.service import RiskPolicyService
from app.scenarios.service import ScenarioService
from app.scenarios.types import ScenarioKind, ShockTargetType, ShockUnit
from app.snapshots.service import SnapshotService
from app.valuation.service import HistoricalValuationService
from tests.conftest import FUND_ID, INSTRUMENT_ID
from tests.governance.factories import ADVISOR_ID, ANALYST_ID, MANAGER_ID, seed_roles
from tests.snapshots.factories import instant, post

AS_OF = datetime(2026, 3, 31, 20, tzinfo=UTC)
POLICY_ID = UUID("d1000000-0000-4000-8000-000000000001")
RULE_ID = UUID("d2000000-0000-4000-8000-000000000001")
SCENARIO_ID = UUID("d3000000-0000-4000-8000-000000000001")


@dataclass
class PriceProvider:
    prices: tuple[ProviderPrice, ...]
    name: str = "release-fixture"

    def fetch_prices(self, request: PriceRequest) -> tuple[ProviderPrice, ...]:
        return self.prices


class EvidenceProvider(ModelProvider):
    def __init__(self) -> None:
        self.turns = iter(
            (
                ModelTurn(
                    "release-1",
                    None,
                    (
                        ToolCall(
                            "exposure",
                            "get_exposure",
                            json.dumps(
                                {
                                    "as_of": AS_OF.isoformat(),
                                    "max_price_age_seconds": 86400,
                                }
                            ),
                        ),
                    ),
                ),
                ModelTurn(
                    "release-2",
                    None,
                    (
                        ToolCall(
                            "breaches",
                            "get_policy_breaches",
                            json.dumps({"as_of": AS_OF.isoformat()}),
                        ),
                    ),
                ),
                ModelTurn(
                    "release-3",
                    None,
                    (
                        ToolCall(
                            "scenario",
                            "run_scenario",
                            json.dumps(
                                {
                                    "scenario_id": str(SCENARIO_ID),
                                    "as_of": AS_OF.isoformat(),
                                    "max_price_age_seconds": 86400,
                                }
                            ),
                        ),
                    ),
                ),
                ModelTurn(
                    "release-4",
                    (
                        "Technology exposure exceeds its warning threshold, and the AAPL shock "
                        "reduces projected portfolio value. The proposal was therefore rejected."
                    ),
                    (),
                ),
            )
        )

    @property
    def model(self) -> str:
        return "release-evidence-provider"

    def start(
        self,
        instructions: str,
        user_prompt: str,
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn:
        return next(self.turns)

    def continue_with_tools(
        self,
        instructions: str,
        previous_response_id: str,
        tool_outputs: tuple[tuple[str, str], ...],
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn:
        return next(self.turns)


def test_release_golden_path_is_grounded_deterministic_and_auditable(session) -> None:
    seed_roles(session)
    post(
        session,
        1,
        TransactionType.OPENING_CASH,
        effective_at=instant(3, 1),
        amount=Decimal("1000"),
    )
    post(
        session,
        2,
        TransactionType.BUY,
        effective_at=instant(3, 2),
        instrument=True,
        quantity=Decimal("8"),
        unit_price=Decimal("50"),
    )

    snapshots = SnapshotService(session)
    snapshot = snapshots.create(
        fund_id=FUND_ID, as_of=AS_OF, account_id=None, actor_user_id=ANALYST_ID
    ).snapshot
    assert snapshots.verify(snapshot.id).reproducible is True

    observed_at = AS_OF - timedelta(hours=1)
    market_batch = MarketDataService(session).ingest(
        PriceProvider(
            (
                ProviderPrice(
                    "AAPL",
                    observed_at,
                    Decimal("100"),
                    source_metadata={"fixture": "release-golden-path"},
                ),
            )
        ),
        PriceRequest(("AAPL",), observed_at, AS_OF),
        AS_OF,
    )
    assert market_batch.inserted_count == 1

    valuation = HistoricalValuationService(session).value_at(FUND_ID, AS_OF, timedelta(days=1))
    assert valuation.cash_value == Decimal("600")
    assert valuation.securities_value == Decimal("800")
    assert valuation.portfolio_value == Decimal("1400")
    assert valuation.unrealized_pnl == Decimal("400")
    assert valuation.reconstruction_input_hash == snapshot.canonical_input_hash

    session.add(
        InstrumentClassificationRecord(
            id=UUID("d0000000-0000-4000-8000-000000000001"),
            instrument_id=INSTRUMENT_ID,
            sector="Technology",
            asset_class="Equity",
            geography="United States",
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=None,
            source="release-fixture",
            source_metadata={"method": "deterministic"},
            recorded_at=AS_OF,
        )
    )
    session.commit()
    exposure = ExposureService(session).calculate(valuation)
    technology_weight = next(
        item.weight for item in exposure.sector_exposure if item.category == "Technology"
    )
    assert technology_weight == Decimal("800") / Decimal("1400")

    values = tuple(
        ValueObservation(AS_OF - timedelta(days=5 - index), Decimal(value))
        for index, value in enumerate(("1000", "1010", "990", "1030", "1020", "1400"))
    )
    analytics = AnalyticsEngine().analyze(values)
    portfolio_returns = tuple(item.period_return for item in analytics.returns)
    benchmark_returns = (
        Decimal("0.005"),
        Decimal("-0.01"),
        Decimal("0.02"),
        Decimal("-0.005"),
        Decimal("0.01"),
    )
    risk = RiskEngine().calculate(
        portfolio_returns,
        benchmark_returns,
        valuation.portfolio_value,
        exposure,
        confidence_level=Decimal("0.8"),
    )
    assert risk.observation_count == 5
    assert risk.beta is not None

    session.add(
        RiskPolicy(
            id=POLICY_ID,
            fund_id=FUND_ID,
            name="Release concentration policy",
            version=1,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=None,
            created_at=AS_OF,
            created_by_user_id=MANAGER_ID,
        )
    )
    session.flush()
    session.add(
        RiskPolicyRule(
            id=RULE_ID,
            policy_id=POLICY_ID,
            metric_key="sector.Technology",
            operator=PolicyOperator.MAX,
            threshold=Decimal("0.50"),
            unit="ratio",
            explanation_template="Technology exposure must remain at or below 50%.",
            severity=PolicyRuleSeverity.WARNING,
        )
    )
    session.commit()
    evaluation_id, evaluation_items = RiskPolicyService(session).evaluate_and_record(
        FUND_ID,
        POLICY_ID,
        AS_OF,
        {"sector.Technology": technology_weight},
        AS_OF,
    )
    assert evaluation_items[0].status is PolicyEvaluationStatus.BREACH

    session.add(
        ScenarioDefinitionRecord(
            id=SCENARIO_ID,
            fund_id=FUND_ID,
            name="AAPL down 25 percent",
            version=1,
            kind=ScenarioKind.HYPOTHETICAL,
            description="Release-validation security shock.",
            source_metadata={"fixture": "release-golden-path"},
            created_at=AS_OF,
            created_by_user_id=ANALYST_ID,
        )
    )
    session.flush()
    session.add(
        ScenarioShockRecord(
            id=UUID("d4000000-0000-4000-8000-000000000001"),
            scenario_id=SCENARIO_ID,
            target_type=ShockTargetType.SECURITY,
            target=str(INSTRUMENT_ID),
            magnitude=Decimal("-0.25"),
            unit=ShockUnit.RELATIVE_RETURN,
            sequence=1,
        )
    )
    session.commit()
    scenario = ScenarioService(session).execute(
        SCENARIO_ID,
        valuation,
        portfolio_returns,
        benchmark_returns,
        POLICY_ID,
        AS_OF,
        confidence_level=Decimal("0.8"),
    )
    assert scenario.analysis.scenario.pnl_impact == Decimal("-200")

    proposal_input = ProposalVersionInput(
        "Increase AAPL despite concentration warning",
        "Committee should explicitly weigh concentration against conviction.",
        snapshot.canonical_input_hash,
        AS_OF,
        (
            ProposalLineInput(
                INSTRUMENT_ID,
                ProposalAction.BUY,
                technology_weight,
                Decimal("0.65"),
                Decimal("110"),
                "Increase the target weight after documented review.",
            ),
        ),
    )
    proposals = ProposalService(session)
    proposal = proposals.create(FUND_ID, ANALYST_ID, proposal_input, AS_OF)
    proposals.record_analysis(
        proposal.id, ANALYST_ID, 1, evaluation_id, scenario.run_id, AS_OF + timedelta(minutes=1)
    )
    proposals.submit(proposal.id, ANALYST_ID, 2, AS_OF + timedelta(minutes=2))
    proposals.start_review(proposal.id, MANAGER_ID, 3, AS_OF + timedelta(minutes=3))
    proposals.record_review(
        proposal.id,
        ADVISOR_ID,
        4,
        ReviewRecommendation.OPPOSE,
        "The documented concentration warning outweighs the thesis.",
        AS_OF + timedelta(minutes=4),
    )
    rejected = proposals.reject(
        proposal.id,
        MANAGER_ID,
        5,
        "Rejected because the proposal increases an existing concentration breach.",
        AS_OF + timedelta(minutes=5),
    )
    assert rejected.status is ProposalStatus.REJECTED

    ai = AIIntelligenceService(
        session,
        EvidenceProvider(),
        ToolRegistry(AuthorizationService(session), SqlReadOnlyPortfolioTools(session)),
    )
    answer = ai.ask(
        ANALYST_ID,
        FUND_ID,
        "Explain the concentration breach, scenario impact, and proposal decision.",
    )
    assert answer.status is ConversationStatus.COMPLETED
    source_types = {source.source_type for source in answer.sources}
    assert {
        "portfolio_reconstruction",
        "market_price",
        "instrument_classification",
        "risk_evaluation",
        "risk_policy",
        "risk_policy_rule",
        "scenario_definition",
    } <= source_types
    assert session.scalar(select(func.count()).select_from(AIToolCall)) == 3
    assert session.scalar(select(func.count()).select_from(ScenarioRun)) == 1

    audit_actions = set(session.scalars(select(AuditEvent.action)).all())
    assert {
        "PORTFOLIO_SNAPSHOT_CREATED",
        "proposal.created",
        "proposal.analyzed",
        "proposal.submitted",
        "proposal.review_started",
        "proposal.review_recorded",
        "proposal.rejected",
        "AI_CONVERSATION_STARTED",
        "AI_CONVERSATION_COMPLETED",
    } <= audit_actions
