import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RiskEvaluation, RiskEvaluationItem, RiskPolicy, RiskPolicyRule
from app.risk.errors import RiskError
from app.risk.policy import PolicyEngine, PolicyEvaluationItem, PolicyRuleInput

CALCULATION_VERSION = "risk-policy-v1"


class RiskPolicyService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def evaluate_and_record(
        self,
        fund_id: UUID,
        policy_id: UUID,
        as_of: datetime,
        metrics: dict[str, Decimal],
        created_at: datetime,
    ) -> tuple[UUID, tuple[PolicyEvaluationItem, ...]]:
        self._require_aware(as_of)
        self._require_aware(created_at)
        policy = self.session.get(RiskPolicy, policy_id)
        if policy is None or policy.fund_id != fund_id:
            raise RiskError("risk policy does not belong to the requested fund")
        effective_from = self._aware(policy.effective_from)
        effective_to = self._aware(policy.effective_to) if policy.effective_to else None
        if as_of < effective_from or (effective_to is not None and as_of >= effective_to):
            raise RiskError("risk policy is not effective at the evaluation cutoff")
        rules = self.session.scalars(
            select(RiskPolicyRule).where(RiskPolicyRule.policy_id == policy_id)
        ).all()
        domain_rules = tuple(
            PolicyRuleInput(
                row.id,
                row.metric_key,
                row.operator,
                row.threshold,
                row.unit,
                row.explanation_template,
            )
            for row in rules
        )
        results = PolicyEngine().evaluate(domain_rules, metrics)
        input_hash = self._hash(policy_id, as_of, metrics)
        existing = self.session.scalar(
            select(RiskEvaluation).where(
                RiskEvaluation.policy_id == policy_id,
                RiskEvaluation.as_of == as_of,
                RiskEvaluation.input_hash == input_hash,
            )
        )
        if existing is not None:
            return existing.id, results
        evaluation = RiskEvaluation(
            id=uuid4(),
            fund_id=fund_id,
            policy_id=policy_id,
            as_of=as_of,
            input_hash=input_hash,
            calculation_version=CALCULATION_VERSION,
            created_at=created_at,
        )
        self.session.add(evaluation)
        self.session.flush()
        for result in results:
            self.session.add(
                RiskEvaluationItem(
                    id=uuid4(),
                    evaluation_id=evaluation.id,
                    rule_id=result.rule_id,
                    status=result.status,
                    observed_value=result.observed_value,
                    threshold=result.threshold,
                    breach_amount=result.breach_amount,
                    unit=result.unit,
                    explanation=result.explanation,
                )
            )
        self.session.commit()
        return evaluation.id, results

    @staticmethod
    def _hash(policy_id: UUID, as_of: datetime, metrics: dict[str, Decimal]) -> str:
        payload = {
            "policy_id": str(policy_id),
            "as_of": as_of.astimezone(UTC).isoformat(),
            "metrics": {key: str(value) for key, value in sorted(metrics.items())},
            "calculation_version": CALCULATION_VERSION,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None:
            raise RiskError("evaluation timestamps must be timezone-aware")

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
