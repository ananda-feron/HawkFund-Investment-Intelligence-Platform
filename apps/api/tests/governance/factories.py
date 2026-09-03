from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.governance.types import ProposalAction, ProposalLineInput, ProposalVersionInput
from app.models import (
    RiskEvaluation,
    RiskEvaluationItem,
    RiskPolicy,
    RiskPolicyRule,
    Role,
    User,
    UserRole,
)
from app.risk.policy import (
    PolicyEvaluationStatus,
    PolicyOperator,
    PolicyRuleSeverity,
)
from tests.conftest import FUND_ID, INSTRUMENT_ID

AS_OF = datetime(2026, 3, 31, 20, tzinfo=UTC)
ANALYST_ID = UUID("c0000000-0000-4000-8000-000000000001")
MANAGER_ID = UUID("c0000000-0000-4000-8000-000000000002")
ADVISOR_ID = UUID("c0000000-0000-4000-8000-000000000003")


def seed_roles(session: Session) -> None:
    users = (
        (ANALYST_ID, "analyst", "Analyst"),
        (MANAGER_ID, "manager", "Manager"),
        (ADVISOR_ID, "advisor", "Advisor"),
    )
    for index, (user_id, code, name) in enumerate(users, start=1):
        role_id = UUID(f"c1000000-0000-4000-8000-{index:012d}")
        session.add(
            User(
                id=user_id,
                email=f"{code}@test.local",
                display_name=name,
                is_active=True,
                created_at=AS_OF,
            )
        )
        session.add(Role(id=role_id, code=code, name=name))
        session.flush()
        session.add(UserRole(user_id=user_id, role_id=role_id, fund_id=FUND_ID))
    session.commit()


def content(title: str = "Increase AAPL") -> ProposalVersionInput:
    return ProposalVersionInput(
        title,
        "Durable competitive position supports a larger allocation.",
        "d" * 64,
        AS_OF,
        (
            ProposalLineInput(
                INSTRUMENT_ID,
                ProposalAction.BUY,
                Decimal("0.04"),
                Decimal("0.07"),
                Decimal("50000"),
                "Increase target weight after committee review.",
            ),
        ),
    )


def seed_evaluation(
    session: Session,
    status: PolicyEvaluationStatus = PolicyEvaluationStatus.PASS,
    severity: PolicyRuleSeverity = PolicyRuleSeverity.BLOCKING,
    number: int = 1,
) -> UUID:
    policy_id = UUID(f"c2000000-0000-4000-8000-{number:012d}")
    rule_id = UUID(f"c3000000-0000-4000-8000-{number:012d}")
    evaluation_id = UUID(f"c4000000-0000-4000-8000-{number:012d}")
    session.add(
        RiskPolicy(
            id=policy_id,
            fund_id=FUND_ID,
            name=f"Policy {number}",
            version=1,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            effective_to=None,
            created_at=AS_OF,
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
            explanation_template="Technology limit",
            severity=severity,
        )
    )
    session.flush()
    session.add(
        RiskEvaluation(
            id=evaluation_id,
            fund_id=FUND_ID,
            policy_id=policy_id,
            as_of=AS_OF,
            input_hash=f"{number:064x}",
            calculation_version="test",
            created_at=AS_OF,
        )
    )
    session.flush()
    session.add(
        RiskEvaluationItem(
            id=UUID(f"c5000000-0000-4000-8000-{number:012d}"),
            evaluation_id=evaluation_id,
            rule_id=rule_id,
            status=status,
            observed_value=Decimal("0.34")
            if status is PolicyEvaluationStatus.PASS
            else Decimal("0.40"),
            threshold=Decimal("0.35"),
            breach_amount=Decimal("0")
            if status is PolicyEvaluationStatus.PASS
            else Decimal("0.05"),
            unit="ratio",
            explanation="test result",
        )
    )
    session.commit()
    return evaluation_id
