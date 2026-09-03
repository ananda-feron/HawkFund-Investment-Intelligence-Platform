from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.ai.errors import DataUnavailable
from app.ai.types import SourceReference, ToolResult
from app.exposures.service import ExposureService
from app.exposures.types import CategoryExposure
from app.models import (
    InstrumentClassificationRecord,
    PortfolioSnapshot,
    RiskEvaluation,
    RiskEvaluationItem,
    RiskPolicy,
    RiskPolicyRule,
    ScenarioDefinitionRecord,
)
from app.risk.policy import PolicyEvaluationStatus
from app.scenarios.service import ScenarioService
from app.snapshots.types import SnapshotStatus
from app.valuation.service import HistoricalValuationService
from app.valuation.types import ValuationResult


class SqlReadOnlyPortfolioTools:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_holdings(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        snapshot = self._snapshot(fund_id, as_of)
        positions = snapshot.canonical_state.get("positions")
        cash = snapshot.canonical_state.get("cash")
        if not isinstance(positions, list):
            raise DataUnavailable("snapshot position evidence is unavailable")
        return ToolResult(
            {"as_of": self._utc(snapshot.as_of).isoformat(), "cash": cash, "holdings": positions},
            (self._snapshot_source(snapshot),),
        )

    def get_portfolio_snapshot(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        snapshot = self._snapshot(fund_id, as_of)
        return ToolResult(
            {
                "snapshot_id": str(snapshot.id),
                "as_of": self._utc(snapshot.as_of).isoformat(),
                "revision": snapshot.revision,
                "calculation_version": snapshot.calculation_version,
                "state": snapshot.canonical_state,
            },
            (self._snapshot_source(snapshot),),
        )

    def get_exposure(
        self, fund_id: UUID, as_of: datetime, max_price_age_seconds: int
    ) -> ToolResult:
        valuation = self._valuation(fund_id, as_of, max_price_age_seconds)
        exposure = ExposureService(self.session).calculate(valuation)
        sources = list(self._valuation_sources(valuation))
        sources.extend(self._classification_sources(fund_id, valuation.as_of))
        return ToolResult(
            {
                "as_of": valuation.as_of.isoformat(),
                "portfolio_value": str(exposure.portfolio_value),
                "cash_value": str(exposure.cash_value),
                "position_weights": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "market_value": str(item.market_value),
                        "weight": str(item.weight),
                    }
                    for item in exposure.position_weights
                ],
                "sector": self._categories(exposure.sector_exposure),
                "asset_class": self._categories(exposure.asset_allocation),
                "geography": self._categories(exposure.geographic_exposure),
                "largest_position_weight": str(exposure.largest_position_weight),
                "herfindahl_index": str(exposure.herfindahl_index),
            },
            tuple(sources),
            exposure.warnings + valuation.warnings,
        )

    def get_risk(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        evaluation = self._risk_evaluation(fund_id, as_of)
        rows = self.session.execute(
            select(RiskEvaluationItem, RiskPolicyRule)
            .join(RiskPolicyRule, RiskPolicyRule.id == RiskEvaluationItem.rule_id)
            .where(
                RiskEvaluationItem.evaluation_id == evaluation.id,
                RiskPolicyRule.metric_key.like("risk.%"),
            )
        ).all()
        if not rows:
            raise DataUnavailable("no persisted risk metrics are available for this cutoff")
        return ToolResult(
            {
                "as_of": self._utc(evaluation.as_of).isoformat(),
                "calculation_version": evaluation.calculation_version,
                "metrics": [self._policy_item(item, rule) for item, rule in rows],
            },
            self._risk_sources(evaluation, tuple(rule for _, rule in rows)),
        )

    def get_policy_breaches(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        evaluation = self._risk_evaluation(fund_id, as_of)
        rows = self.session.execute(
            select(RiskEvaluationItem, RiskPolicyRule)
            .join(RiskPolicyRule, RiskPolicyRule.id == RiskEvaluationItem.rule_id)
            .where(RiskEvaluationItem.evaluation_id == evaluation.id)
        ).all()
        reportable = tuple(
            (item, rule)
            for item, rule in rows
            if item.status in {PolicyEvaluationStatus.BREACH, PolicyEvaluationStatus.UNAVAILABLE}
        )
        return ToolResult(
            {
                "as_of": self._utc(evaluation.as_of).isoformat(),
                "breaches_and_unavailable": [
                    self._policy_item(item, rule) for item, rule in reportable
                ],
                "count": len(reportable),
            },
            self._risk_sources(evaluation, tuple(rule for _, rule in rows)),
        )

    def run_scenario(
        self,
        fund_id: UUID,
        scenario_id: UUID,
        as_of: datetime,
        max_price_age_seconds: int,
    ) -> ToolResult:
        valuation = self._valuation(fund_id, as_of, max_price_age_seconds)
        try:
            result = ScenarioService(self.session).preview(scenario_id, valuation)
        except ValueError as error:
            raise DataUnavailable(f"scenario preview is unavailable: {error}") from error
        definition = self.session.get(ScenarioDefinitionRecord, scenario_id)
        if definition is None:
            raise DataUnavailable("scenario definition is unavailable")
        sources = list(self._valuation_sources(valuation))
        sources.append(
            SourceReference(
                "scenario_definition",
                str(definition.id),
                f"{definition.name} version {definition.version}",
                None,
                result.canonical_input_hash,
            )
        )
        return ToolResult(
            {
                "scenario_id": str(definition.id),
                "scenario_name": definition.name,
                "scenario_version": definition.version,
                "as_of": result.as_of.isoformat(),
                "baseline_portfolio_value": str(result.baseline.portfolio_value),
                "projected_portfolio_value": str(result.projected.portfolio_value),
                "pnl_impact": str(result.pnl_impact),
                "portfolio_return_impact": str(result.portfolio_return_impact),
                "positions": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "baseline_market_value": str(item.baseline_market_value),
                        "projected_market_value": str(item.projected_market_value),
                        "pnl_impact": str(item.pnl_impact),
                        "return_impact": str(item.return_impact),
                    }
                    for item in result.positions
                ],
            },
            tuple(sources),
            result.warnings + valuation.warnings,
        )

    def _snapshot(self, fund_id: UUID, as_of: datetime) -> PortfolioSnapshot:
        snapshot = self.session.scalar(
            select(PortfolioSnapshot)
            .where(
                PortfolioSnapshot.fund_id == fund_id,
                PortfolioSnapshot.account_id.is_(None),
                PortfolioSnapshot.status == SnapshotStatus.CURRENT,
                PortfolioSnapshot.as_of <= as_of,
            )
            .order_by(PortfolioSnapshot.as_of.desc(), PortfolioSnapshot.revision.desc())
            .limit(1)
        )
        if snapshot is None:
            raise DataUnavailable(
                "no reproducible portfolio snapshot exists at or before the cutoff"
            )
        return snapshot

    def _valuation(
        self, fund_id: UUID, as_of: datetime, max_price_age_seconds: int
    ) -> ValuationResult:
        try:
            return HistoricalValuationService(self.session).value_at(
                fund_id, as_of, timedelta(seconds=max_price_age_seconds)
            )
        except ValueError as error:
            raise DataUnavailable(f"point-in-time valuation is unavailable: {error}") from error

    def _risk_evaluation(self, fund_id: UUID, as_of: datetime) -> RiskEvaluation:
        evaluation = self.session.scalar(
            select(RiskEvaluation)
            .where(RiskEvaluation.fund_id == fund_id, RiskEvaluation.as_of <= as_of)
            .order_by(RiskEvaluation.as_of.desc(), RiskEvaluation.created_at.desc())
            .limit(1)
        )
        if evaluation is None:
            raise DataUnavailable(
                "no persisted policy/risk evaluation exists at or before the cutoff"
            )
        return evaluation

    def _classification_sources(
        self, fund_id: UUID, as_of: datetime
    ) -> tuple[SourceReference, ...]:
        rows = self.session.scalars(
            select(InstrumentClassificationRecord)
            .where(
                InstrumentClassificationRecord.effective_from <= as_of,
                or_(
                    InstrumentClassificationRecord.effective_to.is_(None),
                    InstrumentClassificationRecord.effective_to > as_of,
                ),
            )
            .order_by(InstrumentClassificationRecord.instrument_id)
        ).all()
        return tuple(
            SourceReference(
                "instrument_classification",
                str(item.id),
                f"{item.instrument_id}: {item.sector}/{item.asset_class}/{item.geography}",
                self._utc(item.effective_from),
            )
            for item in rows
        )

    @staticmethod
    def _snapshot_source(snapshot: PortfolioSnapshot) -> SourceReference:
        return SourceReference(
            "portfolio_snapshot",
            str(snapshot.id),
            f"Portfolio snapshot revision {snapshot.revision}",
            SqlReadOnlyPortfolioTools._utc(snapshot.as_of),
            snapshot.canonical_input_hash,
        )

    @staticmethod
    def _valuation_sources(valuation: ValuationResult) -> tuple[SourceReference, ...]:
        return tuple(
            SourceReference(
                "market_price",
                str(item.quote.observation_id),
                f"{item.instrument_id} {item.quote.price_type.value} from {item.quote.provider}",
                item.quote.observed_at,
            )
            for item in valuation.positions
        ) + (
            SourceReference(
                "portfolio_reconstruction",
                valuation.reconstruction_input_hash,
                "Deterministic portfolio reconstruction",
                valuation.as_of,
                valuation.reconstruction_input_hash,
            ),
        )

    def _risk_sources(
        self, evaluation: RiskEvaluation, rules: tuple[RiskPolicyRule, ...]
    ) -> tuple[SourceReference, ...]:
        policy = self.session.get(RiskPolicy, evaluation.policy_id)
        sources = [
            SourceReference(
                "risk_evaluation",
                str(evaluation.id),
                f"Risk evaluation {evaluation.calculation_version}",
                self._utc(evaluation.as_of),
                evaluation.input_hash,
            )
        ]
        if policy is not None:
            sources.append(
                SourceReference(
                    "risk_policy",
                    str(policy.id),
                    f"{policy.name} version {policy.version}",
                    self._utc(policy.effective_from),
                )
            )
        sources.extend(
            SourceReference(
                "risk_policy_rule",
                str(rule.id),
                rule.metric_key,
                None,
            )
            for rule in rules
        )
        return tuple(sources)

    @staticmethod
    def _policy_item(item: RiskEvaluationItem, rule: RiskPolicyRule) -> dict[str, Any]:
        return {
            "metric_key": rule.metric_key,
            "status": item.status.value,
            "observed_value": None if item.observed_value is None else str(item.observed_value),
            "threshold": str(item.threshold),
            "breach_amount": None if item.breach_amount is None else str(item.breach_amount),
            "unit": item.unit,
            "severity": rule.severity.value,
            "explanation": item.explanation,
        }

    @staticmethod
    def _categories(rows: tuple[CategoryExposure, ...]) -> list[dict[str, str]]:
        return [
            {
                "category": item.category,
                "market_value": str(item.market_value),
                "weight": str(item.weight),
            }
            for item in rows
        ]

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
