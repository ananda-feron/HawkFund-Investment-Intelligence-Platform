from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.exposures.service import ExposureService
from app.exposures.types import ExposureResult
from app.risk.engine import RiskEngine
from app.risk.policy import PolicyEvaluationItem, portfolio_risk_metrics
from app.risk.service import RiskPolicyService
from app.risk.types import RiskResult
from app.valuation.types import ValuationResult


@dataclass(frozen=True, slots=True)
class PortfolioRiskAnalysis:
    exposure: ExposureResult
    risk: RiskResult
    evaluation_id: UUID
    policy_results: tuple[PolicyEvaluationItem, ...]


class PortfolioRiskPipeline:
    def __init__(self, session: Session) -> None:
        self.session = session

    def analyze(
        self,
        valuation: ValuationResult,
        portfolio_returns: Iterable[Decimal],
        benchmark_returns: Iterable[Decimal],
        policy_id: UUID,
        created_at: datetime,
        confidence_level: Decimal = Decimal("0.95"),
        annualization_periods: int = 252,
        top_n: int = 10,
    ) -> PortfolioRiskAnalysis:
        exposure = ExposureService(self.session).calculate(valuation, top_n)
        risk = RiskEngine().calculate(
            portfolio_returns,
            benchmark_returns,
            valuation.portfolio_value,
            exposure,
            confidence_level,
            annualization_periods,
        )
        evaluation_id, policy_results = RiskPolicyService(self.session).evaluate_and_record(
            valuation.fund_id,
            policy_id,
            valuation.as_of,
            portfolio_risk_metrics(exposure, risk),
            created_at,
        )
        return PortfolioRiskAnalysis(exposure, risk, evaluation_id, policy_results)
