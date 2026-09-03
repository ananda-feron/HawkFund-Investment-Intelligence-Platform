from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.governance.errors import (
    AuthorizationDenied,
    ConcurrentProposalUpdate,
    PolicyEvidenceRequired,
)
from app.governance.service import ProposalService
from app.governance.types import ProposalStatus, ReviewRecommendation
from app.models import AuditEvent, ProposalTransition, ProposalVersion, Role, UserRole
from app.risk.policy import PolicyEvaluationStatus, PolicyRuleSeverity
from tests.conftest import FUND_ID
from tests.governance.factories import (
    ADVISOR_ID,
    ANALYST_ID,
    AS_OF,
    MANAGER_ID,
    content,
    seed_evaluation,
    seed_roles,
)


def test_full_workflow_preserves_history_provenance_and_separation_of_duties(session) -> None:
    seed_roles(session)
    evaluation_id = seed_evaluation(session)
    service = ProposalService(session)
    proposal = service.create(FUND_ID, ANALYST_ID, content(), AS_OF)
    service.record_analysis(proposal.id, ANALYST_ID, 1, evaluation_id, None, AS_OF)
    service.submit(proposal.id, ANALYST_ID, 2, AS_OF + timedelta(minutes=1))
    service.start_review(proposal.id, MANAGER_ID, 3, AS_OF + timedelta(minutes=2))
    service.record_review(
        proposal.id,
        ADVISOR_ID,
        4,
        ReviewRecommendation.SUPPORT,
        "Supported after reviewing the bound risk evidence.",
        AS_OF + timedelta(minutes=3),
    )

    approved = service.approve(
        proposal.id, MANAGER_ID, 5, "Approved within policy.", AS_OF + timedelta(minutes=4)
    )

    assert approved.status is ProposalStatus.APPROVED
    assert approved.row_version == 6
    assert session.scalar(select(func.count()).select_from(ProposalTransition)) == 6
    assert session.scalar(select(func.count()).select_from(AuditEvent)) == 6
    final_transition = session.scalar(
        select(ProposalTransition)
        .where(ProposalTransition.proposal_id == proposal.id)
        .order_by(ProposalTransition.resulting_row_version.desc())
        .limit(1)
    )
    assert final_transition is not None
    assert final_transition.decision_provenance["risk_evaluation_id"] == str(evaluation_id)


def test_blocking_evidence_stale_write_and_self_approval_are_rejected(session) -> None:
    seed_roles(session)
    evaluation_id = seed_evaluation(
        session, PolicyEvaluationStatus.BREACH, PolicyRuleSeverity.BLOCKING
    )
    second_evaluation_id = seed_evaluation(session, number=2)
    service = ProposalService(session)
    proposal = service.create(FUND_ID, ANALYST_ID, content(), AS_OF)
    service.record_analysis(proposal.id, ANALYST_ID, 1, evaluation_id, None, AS_OF)
    with pytest.raises(PolicyEvidenceRequired):
        service.submit(proposal.id, ANALYST_ID, 2, AS_OF)
    with pytest.raises(ConcurrentProposalUpdate):
        service.record_analysis(proposal.id, ANALYST_ID, 1, second_evaluation_id, None, AS_OF)
    with pytest.raises(AuthorizationDenied):
        service.approve(proposal.id, ANALYST_ID, 2, "self", AS_OF)


def test_new_revision_invalidates_prior_analysis(session) -> None:
    seed_roles(session)
    evaluation_id = seed_evaluation(session)
    service = ProposalService(session)
    proposal = service.create(FUND_ID, ANALYST_ID, content(), AS_OF)
    service.record_analysis(proposal.id, ANALYST_ID, 1, evaluation_id, None, AS_OF)
    service.submit(proposal.id, ANALYST_ID, 2, AS_OF)
    service.request_changes(proposal.id, ADVISOR_ID, 3, "Clarify valuation support.", AS_OF)
    revised = service.revise(proposal.id, ANALYST_ID, 4, content("Revised AAPL"), AS_OF)

    assert revised.current_version == 2
    assert session.scalar(select(func.count()).select_from(ProposalVersion)) == 2
    with pytest.raises(PolicyEvidenceRequired):
        service.submit(proposal.id, ANALYST_ID, 5, AS_OF)


def test_warning_breach_does_not_block_submission(session) -> None:
    seed_roles(session)
    evaluation_id = seed_evaluation(
        session,
        PolicyEvaluationStatus.BREACH,
        PolicyRuleSeverity.WARNING,
    )
    service = ProposalService(session)
    proposal = service.create(FUND_ID, ANALYST_ID, content(), AS_OF)
    service.record_analysis(proposal.id, ANALYST_ID, 1, evaluation_id, None, AS_OF)

    submitted = service.submit(proposal.id, ANALYST_ID, 2, AS_OF)

    assert submitted.status is ProposalStatus.SUBMITTED


def test_multi_role_author_cannot_self_approve(session) -> None:
    seed_roles(session)
    manager_role = session.scalar(select(Role).where(Role.code == "manager"))
    assert manager_role is not None
    session.add(UserRole(user_id=ANALYST_ID, role_id=manager_role.id, fund_id=FUND_ID))
    session.commit()
    service = ProposalService(session)
    proposal = service.create(FUND_ID, ANALYST_ID, content(), AS_OF)

    with pytest.raises(AuthorizationDenied, match="own proposal"):
        service.approve(proposal.id, ANALYST_ID, 1, "self approval", AS_OF)
