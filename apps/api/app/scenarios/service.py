import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.exposures.service import ExposureService
from app.models import (
    InstrumentRiskSensitivity,
    RiskPolicy,
    RiskPolicyRule,
    ScenarioDefinitionRecord,
    ScenarioPositionResultRecord,
    ScenarioRun,
    ScenarioShockRecord,
)
from app.risk.policy import PolicyEvaluationItem, PolicyRuleInput
from app.scenarios.comparison import BeforeAfterEngine
from app.scenarios.engine import ScenarioEngine
from app.scenarios.errors import InvalidScenario
from app.scenarios.types import (
    BeforeAfterResult,
    InstrumentSensitivity,
    ScenarioDefinition,
    ScenarioShock,
)
from app.valuation.types import ValuationResult

CALCULATION_VERSION = "scenario-comparison-v1"


@dataclass(frozen=True, slots=True)
class ScenarioExecution:
    run_id: UUID
    analysis: BeforeAfterResult


class ScenarioService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def execute(
        self,
        scenario_id: UUID,
        valuation: ValuationResult,
        portfolio_returns: Iterable[Decimal],
        benchmark_returns: Iterable[Decimal],
        policy_id: UUID,
        created_at: datetime,
        benchmark_scenario_return: Decimal = Decimal("0"),
        confidence_level: Decimal = Decimal("0.95"),
        annualization_periods: int = 252,
        top_n: int = 10,
    ) -> ScenarioExecution:
        self._aware_required(created_at)
        definition = self._definition(scenario_id, valuation.fund_id)
        instrument_ids = {item.instrument_id for item in valuation.positions}
        classifications = ExposureService(self.session).classifications_at(
            instrument_ids, valuation.as_of
        )
        sensitivities = self._sensitivities(instrument_ids, valuation.as_of)
        scenario = ScenarioEngine().apply(valuation, definition, classifications, sensitivities)
        returns = tuple(portfolio_returns)
        benchmark = tuple(benchmark_returns)
        policy = self.session.get(RiskPolicy, policy_id)
        if policy is None or policy.fund_id != valuation.fund_id:
            raise InvalidScenario("risk policy does not belong to the valuation fund")
        effective_from = self._utc(policy.effective_from)
        effective_to = self._utc(policy.effective_to) if policy.effective_to else None
        if valuation.as_of < effective_from or (
            effective_to is not None and valuation.as_of >= effective_to
        ):
            raise InvalidScenario("risk policy is not effective at the scenario cutoff")
        rules = self._rules(policy_id)
        analysis = BeforeAfterEngine().compare(
            scenario,
            classifications,
            returns,
            benchmark,
            rules,
            benchmark_scenario_return,
            confidence_level,
            annualization_periods,
            top_n,
        )
        execution_hash = self._execution_hash(
            scenario.canonical_input_hash,
            returns,
            benchmark,
            policy_id,
            benchmark_scenario_return,
            confidence_level,
            annualization_periods,
            top_n,
        )
        existing = self.session.scalar(
            select(ScenarioRun).where(
                ScenarioRun.scenario_id == scenario_id,
                ScenarioRun.as_of == valuation.as_of,
                ScenarioRun.canonical_input_hash == execution_hash,
            )
        )
        if existing is not None:
            return ScenarioExecution(existing.id, analysis)
        run = ScenarioRun(
            id=uuid4(),
            fund_id=valuation.fund_id,
            scenario_id=scenario_id,
            policy_id=policy_id,
            as_of=valuation.as_of,
            canonical_input_hash=execution_hash,
            calculation_version=CALCULATION_VERSION,
            baseline_value=scenario.baseline.portfolio_value,
            projected_value=scenario.projected.portfolio_value,
            pnl_impact=scenario.pnl_impact,
            portfolio_return_impact=scenario.portfolio_return_impact,
            benchmark_scenario_return=benchmark_scenario_return,
            result_summary=self._summary(analysis),
            created_at=created_at,
        )
        self.session.add(run)
        self.session.flush()
        for item in scenario.positions:
            self.session.add(
                ScenarioPositionResultRecord(
                    id=uuid4(),
                    scenario_run_id=run.id,
                    instrument_id=item.instrument_id,
                    baseline_market_value=item.baseline_market_value,
                    projected_market_value=item.projected_market_value,
                    return_impact=item.return_impact,
                    pnl_impact=item.pnl_impact,
                    contribution_evidence=[
                        {
                            "shock_id": str(contribution.shock_id),
                            "target_type": contribution.target_type.value,
                            "target": contribution.target,
                            "return_impact": str(contribution.return_impact),
                        }
                        for contribution in item.contributions
                    ],
                )
            )
        self.session.commit()
        return ScenarioExecution(run.id, analysis)

    def _definition(self, scenario_id: UUID, fund_id: UUID) -> ScenarioDefinition:
        record = self.session.get(ScenarioDefinitionRecord, scenario_id)
        if record is None or record.fund_id != fund_id:
            raise InvalidScenario("scenario does not belong to the valuation fund")
        rows = self.session.scalars(
            select(ScenarioShockRecord)
            .where(ScenarioShockRecord.scenario_id == scenario_id)
            .order_by(ScenarioShockRecord.sequence, ScenarioShockRecord.id)
        ).all()
        return ScenarioDefinition(
            record.id,
            record.fund_id,
            record.name,
            record.version,
            record.kind,
            tuple(
                ScenarioShock(
                    row.id,
                    row.target_type,
                    row.target,
                    row.magnitude,
                    row.unit,
                    row.sequence,
                )
                for row in rows
            ),
            record.source_metadata,
        )

    def _sensitivities(
        self, instrument_ids: set[UUID], as_of: datetime
    ) -> dict[UUID, InstrumentSensitivity]:
        if not instrument_ids:
            return {}
        rows = self.session.scalars(
            select(InstrumentRiskSensitivity)
            .where(
                InstrumentRiskSensitivity.instrument_id.in_(instrument_ids),
                InstrumentRiskSensitivity.effective_from <= as_of,
                or_(
                    InstrumentRiskSensitivity.effective_to.is_(None),
                    InstrumentRiskSensitivity.effective_to > as_of,
                ),
            )
            .order_by(
                InstrumentRiskSensitivity.instrument_id,
                InstrumentRiskSensitivity.effective_from.desc(),
            )
        ).all()
        output: dict[UUID, InstrumentSensitivity] = {}
        for row in rows:
            output.setdefault(
                row.instrument_id,
                InstrumentSensitivity(
                    row.instrument_id,
                    row.rate_duration,
                    tuple(
                        sorted(
                            (name, Decimal(value)) for name, value in row.factor_loadings.items()
                        )
                    ),
                ),
            )
        return output

    def _rules(self, policy_id: UUID) -> tuple[PolicyRuleInput, ...]:
        rows = self.session.scalars(
            select(RiskPolicyRule).where(RiskPolicyRule.policy_id == policy_id)
        ).all()
        return tuple(
            PolicyRuleInput(
                row.id,
                row.metric_key,
                row.operator,
                row.threshold,
                row.unit,
                row.explanation_template,
            )
            for row in rows
        )

    @staticmethod
    def _summary(analysis: BeforeAfterResult) -> dict[str, object]:
        return {
            "exposure_changes": [
                {
                    "dimension": item.dimension,
                    "category": item.category,
                    "before": str(item.before_weight),
                    "after": str(item.after_weight),
                    "change": str(item.change),
                }
                for item in analysis.exposure_changes
            ],
            "risk_changes": [
                {
                    "metric": item.metric,
                    "before": None if item.before_value is None else str(item.before_value),
                    "after": None if item.after_value is None else str(item.after_value),
                    "change": None if item.change is None else str(item.change),
                }
                for item in analysis.risk_changes
            ],
            "baseline_policy": ScenarioService._policy_summary(analysis.baseline_policy),
            "projected_policy": ScenarioService._policy_summary(analysis.projected_policy),
        }

    @staticmethod
    def _execution_hash(
        scenario_hash: str,
        returns: tuple[Decimal, ...],
        benchmark: tuple[Decimal, ...],
        policy_id: UUID,
        benchmark_scenario_return: Decimal,
        confidence_level: Decimal,
        annualization_periods: int,
        top_n: int,
    ) -> str:
        payload = {
            "scenario_hash": scenario_hash,
            "returns": [str(item) for item in returns],
            "benchmark": [str(item) for item in benchmark],
            "policy_id": str(policy_id),
            "benchmark_scenario_return": str(benchmark_scenario_return),
            "confidence_level": str(confidence_level),
            "annualization_periods": annualization_periods,
            "top_n": top_n,
            "calculation_version": CALCULATION_VERSION,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _policy_summary(
        items: tuple[PolicyEvaluationItem, ...],
    ) -> list[dict[str, str | None]]:
        return [
            {
                "rule_id": str(item.rule_id),
                "metric_key": item.metric_key,
                "status": item.status.value,
                "observed_value": (
                    None if item.observed_value is None else str(item.observed_value)
                ),
                "threshold": str(item.threshold),
                "breach_amount": (None if item.breach_amount is None else str(item.breach_amount)),
                "unit": item.unit,
                "explanation": item.explanation,
            }
            for item in items
        ]

    @staticmethod
    def _aware_required(value: datetime) -> None:
        if value.tzinfo is None:
            raise InvalidScenario("scenario timestamps must be timezone-aware")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
