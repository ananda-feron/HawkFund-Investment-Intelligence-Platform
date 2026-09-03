import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.governance.authorization import AuthorizationService
from app.governance.errors import (
    AuthorizationDenied,
    ConcurrentProposalUpdate,
    InvalidWorkflowTransition,
    PolicyEvidenceRequired,
)
from app.governance.types import (
    GovernanceRole,
    Permission,
    ProposalAction,
    ProposalStatus,
    ProposalVersionInput,
    ReviewRecommendation,
    WorkflowAction,
)
from app.models import (
    AuditEvent,
    InvestmentProposal,
    ProposalAnalysis,
    ProposalLine,
    ProposalReview,
    ProposalTransition,
    ProposalVersion,
    RiskEvaluation,
    RiskEvaluationItem,
    RiskPolicyRule,
    ScenarioRun,
)
from app.risk.policy import PolicyEvaluationStatus, PolicyRuleSeverity


class ProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.authorization = AuthorizationService(session)

    def create(
        self,
        fund_id: UUID,
        actor_user_id: UUID,
        content: ProposalVersionInput,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        role = self.authorization.require(actor_user_id, fund_id, Permission.CREATE_PROPOSAL)
        self._validate_content(content)
        self._aware_required(occurred_at)
        proposal = InvestmentProposal(
            id=uuid4(),
            fund_id=fund_id,
            created_by_user_id=actor_user_id,
            status=ProposalStatus.DRAFT,
            current_version=1,
            row_version=1,
            created_at=occurred_at,
            updated_at=occurred_at,
        )
        self.session.add(proposal)
        self.session.flush()
        version = self._add_version(proposal, actor_user_id, content, occurred_at, None)
        self._history(
            proposal,
            version,
            WorkflowAction.CREATED,
            None,
            ProposalStatus.DRAFT,
            actor_user_id,
            role,
            None,
            {"content_hash": version.content_hash},
            occurred_at,
        )
        self.session.commit()
        return proposal

    def revise(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        content: ProposalVersionInput,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(
            actor_user_id, proposal.fund_id, Permission.REVISE_PROPOSAL
        )
        self._require_owner(proposal, actor_user_id)
        if proposal.status not in {
            ProposalStatus.DRAFT,
            ProposalStatus.CHANGES_REQUESTED,
        }:
            raise InvalidWorkflowTransition(
                "only draft or changes-requested proposals can be revised"
            )
        self._validate_content(content)
        previous = self._current_version(proposal)
        previous_status = proposal.status
        next_version = proposal.current_version + 1
        self._advance(
            proposal,
            expected_row_version,
            ProposalStatus.DRAFT,
            occurred_at,
            current_version=next_version,
        )
        version = self._add_version(proposal, actor_user_id, content, occurred_at, previous.id)
        self._history(
            proposal,
            version,
            WorkflowAction.REVISED,
            previous_status,
            ProposalStatus.DRAFT,
            actor_user_id,
            role,
            None,
            {
                "content_hash": version.content_hash,
                "supersedes_version_id": str(previous.id),
            },
            occurred_at,
        )
        self.session.commit()
        return proposal

    def record_analysis(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        risk_evaluation_id: UUID,
        scenario_run_id: UUID | None,
        occurred_at: datetime,
    ) -> ProposalAnalysis:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(
            actor_user_id, proposal.fund_id, Permission.RECORD_ANALYSIS
        )
        if proposal.status is not ProposalStatus.DRAFT:
            raise InvalidWorkflowTransition("analysis can only be bound to a draft")
        version = self._current_version(proposal)
        risk = self.session.get(RiskEvaluation, risk_evaluation_id)
        if risk is None or risk.fund_id != proposal.fund_id:
            raise PolicyEvidenceRequired("risk evaluation does not belong to the proposal fund")
        if self._utc(risk.as_of) != self._utc(version.portfolio_as_of):
            raise PolicyEvidenceRequired("risk evaluation cutoff differs from proposal cutoff")
        scenario = None
        if scenario_run_id is not None:
            scenario = self.session.get(ScenarioRun, scenario_run_id)
            if (
                scenario is None
                or scenario.fund_id != proposal.fund_id
                or self._utc(scenario.as_of) != self._utc(version.portfolio_as_of)
            ):
                raise PolicyEvidenceRequired("scenario evidence does not match proposal scope")
        evidence_hash = self._analysis_hash(version, risk, scenario)
        existing = self.session.scalar(
            select(ProposalAnalysis).where(
                ProposalAnalysis.proposal_version_id == version.id,
                ProposalAnalysis.evidence_hash == evidence_hash,
            )
        )
        if existing is not None:
            return existing
        self._advance(proposal, expected_row_version, ProposalStatus.DRAFT, occurred_at)
        analysis = ProposalAnalysis(
            id=uuid4(),
            proposal_version_id=version.id,
            risk_evaluation_id=risk.id,
            scenario_run_id=scenario_run_id,
            recorded_by_user_id=actor_user_id,
            recorded_at=occurred_at,
            evidence_hash=evidence_hash,
        )
        self.session.add(analysis)
        self._history(
            proposal,
            version,
            WorkflowAction.ANALYZED,
            ProposalStatus.DRAFT,
            ProposalStatus.DRAFT,
            actor_user_id,
            role,
            None,
            {
                "analysis_id": str(analysis.id),
                "risk_evaluation_id": str(risk.id),
                "scenario_run_id": None if scenario is None else str(scenario.id),
                "evidence_hash": evidence_hash,
            },
            occurred_at,
        )
        self.session.commit()
        return analysis

    def submit(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(
            actor_user_id, proposal.fund_id, Permission.SUBMIT_PROPOSAL
        )
        self._require_owner(proposal, actor_user_id)
        if proposal.status is not ProposalStatus.DRAFT:
            raise InvalidWorkflowTransition("only a draft can be submitted")
        version = self._current_version(proposal)
        analysis = self._required_clear_analysis(version)
        self._advance(proposal, expected_row_version, ProposalStatus.SUBMITTED, occurred_at)
        self._history(
            proposal,
            version,
            WorkflowAction.SUBMITTED,
            ProposalStatus.DRAFT,
            ProposalStatus.SUBMITTED,
            actor_user_id,
            role,
            None,
            self._decision_provenance(version, analysis),
            occurred_at,
        )
        self.session.commit()
        return proposal

    def start_review(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        return self._status_transition(
            proposal_id,
            actor_user_id,
            expected_row_version,
            Permission.START_REVIEW,
            {ProposalStatus.SUBMITTED},
            ProposalStatus.UNDER_REVIEW,
            WorkflowAction.REVIEW_STARTED,
            None,
            occurred_at,
        )

    def record_review(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        recommendation: ReviewRecommendation,
        comment: str,
        occurred_at: datetime,
    ) -> ProposalReview:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(actor_user_id, proposal.fund_id, Permission.RECORD_REVIEW)
        if proposal.status not in {ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW}:
            raise InvalidWorkflowTransition("reviews require a submitted proposal")
        if not comment.strip():
            raise InvalidWorkflowTransition("review comment is required")
        version = self._current_version(proposal)
        self._advance(proposal, expected_row_version, proposal.status, occurred_at)
        review = ProposalReview(
            id=uuid4(),
            proposal_id=proposal.id,
            proposal_version_id=version.id,
            reviewer_user_id=actor_user_id,
            reviewer_role=role.value,
            recommendation=recommendation,
            comment=comment.strip(),
            created_at=occurred_at,
        )
        self.session.add(review)
        self._history(
            proposal,
            version,
            WorkflowAction.REVIEW_RECORDED,
            proposal.status,
            proposal.status,
            actor_user_id,
            role,
            comment.strip(),
            {"review_id": str(review.id), "recommendation": recommendation.value},
            occurred_at,
        )
        self.session.commit()
        return review

    def request_changes(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        reason: str,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        return self._status_transition(
            proposal_id,
            actor_user_id,
            expected_row_version,
            Permission.REQUEST_CHANGES,
            {ProposalStatus.SUBMITTED, ProposalStatus.UNDER_REVIEW},
            ProposalStatus.CHANGES_REQUESTED,
            WorkflowAction.CHANGES_REQUESTED,
            self._required_reason(reason),
            occurred_at,
        )

    def approve(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        reason: str,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(
            actor_user_id, proposal.fund_id, Permission.APPROVE_PROPOSAL
        )
        if actor_user_id == proposal.created_by_user_id:
            raise AuthorizationDenied("proposal authors cannot approve their own proposals")
        if proposal.status is not ProposalStatus.UNDER_REVIEW:
            raise InvalidWorkflowTransition("only a proposal under review can be approved")
        version = self._current_version(proposal)
        analysis = self._required_clear_analysis(version)
        review_count = len(
            self.session.scalars(
                select(ProposalReview).where(ProposalReview.proposal_version_id == version.id)
            ).all()
        )
        if review_count == 0:
            raise InvalidWorkflowTransition("approval requires review history for this version")
        self._advance(proposal, expected_row_version, ProposalStatus.APPROVED, occurred_at)
        provenance = self._decision_provenance(version, analysis)
        provenance["review_count"] = review_count
        self._history(
            proposal,
            version,
            WorkflowAction.APPROVED,
            ProposalStatus.UNDER_REVIEW,
            ProposalStatus.APPROVED,
            actor_user_id,
            role,
            reason.strip() or None,
            provenance,
            occurred_at,
        )
        self.session.commit()
        return proposal

    def reject(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        reason: str,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        return self._status_transition(
            proposal_id,
            actor_user_id,
            expected_row_version,
            Permission.REJECT_PROPOSAL,
            {ProposalStatus.UNDER_REVIEW},
            ProposalStatus.REJECTED,
            WorkflowAction.REJECTED,
            self._required_reason(reason),
            occurred_at,
            prevent_self_decision=True,
        )

    def withdraw(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        reason: str,
        occurred_at: datetime,
    ) -> InvestmentProposal:
        proposal = self._proposal(proposal_id)
        self._require_owner(proposal, actor_user_id)
        return self._status_transition(
            proposal_id,
            actor_user_id,
            expected_row_version,
            Permission.WITHDRAW_PROPOSAL,
            {
                ProposalStatus.DRAFT,
                ProposalStatus.SUBMITTED,
                ProposalStatus.CHANGES_REQUESTED,
            },
            ProposalStatus.WITHDRAWN,
            WorkflowAction.WITHDRAWN,
            self._required_reason(reason),
            occurred_at,
        )

    def _status_transition(
        self,
        proposal_id: UUID,
        actor_user_id: UUID,
        expected_row_version: int,
        permission: Permission,
        allowed_from: set[ProposalStatus],
        to_status: ProposalStatus,
        action: WorkflowAction,
        reason: str | None,
        occurred_at: datetime,
        prevent_self_decision: bool = False,
    ) -> InvestmentProposal:
        proposal = self._proposal(proposal_id)
        role = self.authorization.require(actor_user_id, proposal.fund_id, permission)
        if prevent_self_decision and actor_user_id == proposal.created_by_user_id:
            raise AuthorizationDenied("proposal authors cannot decide their own proposals")
        if proposal.status not in allowed_from:
            raise InvalidWorkflowTransition(
                f"{action.value} is invalid from {proposal.status.value}"
            )
        previous = proposal.status
        version = self._current_version(proposal)
        self._advance(proposal, expected_row_version, to_status, occurred_at)
        self._history(
            proposal,
            version,
            action,
            previous,
            to_status,
            actor_user_id,
            role,
            reason,
            {"content_hash": version.content_hash},
            occurred_at,
        )
        self.session.commit()
        return proposal

    def _advance(
        self,
        proposal: InvestmentProposal,
        expected_row_version: int,
        status: ProposalStatus,
        occurred_at: datetime,
        current_version: int | None = None,
    ) -> None:
        self._aware_required(occurred_at)
        if self._utc(occurred_at) < self._utc(proposal.updated_at):
            raise InvalidWorkflowTransition("workflow timestamp precedes the prior transition")
        next_row_version = expected_row_version + 1
        result = self.session.execute(
            update(InvestmentProposal)
            .where(
                InvestmentProposal.id == proposal.id,
                InvestmentProposal.row_version == expected_row_version,
            )
            .values(
                status=status,
                current_version=(
                    proposal.current_version if current_version is None else current_version
                ),
                row_version=next_row_version,
                updated_at=occurred_at,
            )
        )
        if result.rowcount != 1:
            self.session.rollback()
            raise ConcurrentProposalUpdate("proposal changed; reload before retrying")
        proposal.status = status
        proposal.row_version = next_row_version
        if current_version is not None:
            proposal.current_version = current_version
        proposal.updated_at = occurred_at

    def _add_version(
        self,
        proposal: InvestmentProposal,
        actor_user_id: UUID,
        content: ProposalVersionInput,
        occurred_at: datetime,
        supersedes_version_id: UUID | None,
    ) -> ProposalVersion:
        content_hash = self._content_hash(content)
        version = ProposalVersion(
            id=uuid4(),
            proposal_id=proposal.id,
            version=proposal.current_version,
            title=content.title.strip(),
            thesis=content.thesis.strip(),
            portfolio_input_hash=content.portfolio_input_hash,
            portfolio_as_of=content.portfolio_as_of,
            content_hash=content_hash,
            created_by_user_id=actor_user_id,
            created_at=occurred_at,
            supersedes_version_id=supersedes_version_id,
        )
        self.session.add(version)
        self.session.flush()
        for line in sorted(content.lines, key=lambda item: str(item.instrument_id)):
            self.session.add(
                ProposalLine(
                    id=uuid4(),
                    proposal_version_id=version.id,
                    instrument_id=line.instrument_id,
                    action=line.action,
                    current_weight=line.current_weight,
                    proposed_weight=line.proposed_weight,
                    estimated_notional=line.estimated_notional,
                    rationale=line.rationale.strip(),
                )
            )
        return version

    def _required_clear_analysis(self, version: ProposalVersion) -> ProposalAnalysis:
        analysis = self.session.scalar(
            select(ProposalAnalysis)
            .where(ProposalAnalysis.proposal_version_id == version.id)
            .order_by(ProposalAnalysis.recorded_at.desc(), ProposalAnalysis.id.desc())
            .limit(1)
        )
        if analysis is None:
            raise PolicyEvidenceRequired("current proposal version has no risk analysis")
        rows = self.session.execute(
            select(RiskEvaluationItem, RiskPolicyRule)
            .join(RiskPolicyRule, RiskPolicyRule.id == RiskEvaluationItem.rule_id)
            .where(RiskEvaluationItem.evaluation_id == analysis.risk_evaluation_id)
        ).all()
        if not rows:
            raise PolicyEvidenceRequired("risk evaluation contains no policy results")
        blockers = [
            rule.metric_key
            for item, rule in rows
            if rule.severity is PolicyRuleSeverity.BLOCKING
            and item.status is not PolicyEvaluationStatus.PASS
        ]
        if blockers:
            raise PolicyEvidenceRequired(
                "blocking policy results prevent submission or approval: "
                + ", ".join(sorted(blockers))
            )
        return analysis

    def _history(
        self,
        proposal: InvestmentProposal,
        version: ProposalVersion,
        action: WorkflowAction,
        from_status: ProposalStatus | None,
        to_status: ProposalStatus,
        actor_user_id: UUID,
        actor_role: GovernanceRole,
        reason: str | None,
        provenance: dict[str, object],
        occurred_at: datetime,
    ) -> None:
        transition = ProposalTransition(
            id=uuid4(),
            proposal_id=proposal.id,
            proposal_version_id=version.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            actor_role=actor_role.value,
            reason=reason,
            decision_provenance=provenance,
            occurred_at=occurred_at,
            resulting_row_version=proposal.row_version,
        )
        self.session.add(transition)
        self.session.add(
            AuditEvent(
                id=uuid4(),
                fund_id=proposal.fund_id,
                actor_user_id=actor_user_id,
                action=f"proposal.{action.value.lower()}",
                entity_type="investment_proposal",
                entity_id=proposal.id,
                occurred_at=occurred_at,
                details={
                    "transition_id": str(transition.id),
                    "proposal_version_id": str(version.id),
                    "from_status": None if from_status is None else from_status.value,
                    "to_status": to_status.value,
                    "row_version": proposal.row_version,
                    "provenance": provenance,
                },
            )
        )

    def _proposal(self, proposal_id: UUID) -> InvestmentProposal:
        proposal = self.session.get(InvestmentProposal, proposal_id)
        if proposal is None:
            raise InvalidWorkflowTransition("proposal does not exist")
        return proposal

    def _current_version(self, proposal: InvestmentProposal) -> ProposalVersion:
        version = self.session.scalar(
            select(ProposalVersion).where(
                ProposalVersion.proposal_id == proposal.id,
                ProposalVersion.version == proposal.current_version,
            )
        )
        if version is None:
            raise InvalidWorkflowTransition("current proposal version is missing")
        return version

    @staticmethod
    def _require_owner(proposal: InvestmentProposal, actor_user_id: UUID) -> None:
        if proposal.created_by_user_id != actor_user_id:
            raise AuthorizationDenied("only the proposal author may perform this action")

    @staticmethod
    def _required_reason(reason: str) -> str:
        if not reason.strip():
            raise InvalidWorkflowTransition("a reason is required")
        return reason.strip()

    @staticmethod
    def _validate_content(content: ProposalVersionInput) -> None:
        if not content.title.strip() or not content.thesis.strip():
            raise InvalidWorkflowTransition("proposal title and thesis are required")
        if len(content.portfolio_input_hash) != 64:
            raise InvalidWorkflowTransition("portfolio input hash must contain 64 characters")
        if content.portfolio_as_of.tzinfo is None:
            raise InvalidWorkflowTransition("portfolio cutoff must be timezone-aware")
        if not content.lines:
            raise InvalidWorkflowTransition("at least one proposal line is required")
        if len({item.instrument_id for item in content.lines}) != len(content.lines):
            raise InvalidWorkflowTransition("proposal instruments must be unique")
        for line in content.lines:
            if not (
                0 <= line.current_weight <= 1
                and 0 <= line.proposed_weight <= 1
                and line.estimated_notional >= 0
            ):
                raise InvalidWorkflowTransition("proposal weights or notional are invalid")
            valid_direction = {
                ProposalAction.BUY: line.proposed_weight > line.current_weight,
                ProposalAction.SELL: 0 < line.proposed_weight < line.current_weight,
                ProposalAction.EXIT: line.current_weight > 0 and line.proposed_weight == 0,
                ProposalAction.HOLD: line.proposed_weight == line.current_weight,
            }[line.action]
            if not valid_direction or not line.rationale.strip():
                raise InvalidWorkflowTransition("proposal action or rationale is inconsistent")

    @staticmethod
    def _content_hash(content: ProposalVersionInput) -> str:
        payload = {
            "title": content.title.strip(),
            "thesis": content.thesis.strip(),
            "portfolio_input_hash": content.portfolio_input_hash,
            "portfolio_as_of": content.portfolio_as_of.astimezone(UTC).isoformat(),
            "lines": [
                {
                    "instrument_id": str(item.instrument_id),
                    "action": item.action.value,
                    "current_weight": str(item.current_weight),
                    "proposed_weight": str(item.proposed_weight),
                    "estimated_notional": str(item.estimated_notional),
                    "rationale": item.rationale.strip(),
                }
                for item in sorted(content.lines, key=lambda row: str(row.instrument_id))
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _analysis_hash(
        version: ProposalVersion,
        risk: RiskEvaluation,
        scenario: ScenarioRun | None,
    ) -> str:
        payload = {
            "proposal_content_hash": version.content_hash,
            "portfolio_input_hash": version.portfolio_input_hash,
            "risk_evaluation_id": str(risk.id),
            "risk_input_hash": risk.input_hash,
            "scenario_run_id": None if scenario is None else str(scenario.id),
            "scenario_input_hash": (None if scenario is None else scenario.canonical_input_hash),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _decision_provenance(
        version: ProposalVersion, analysis: ProposalAnalysis
    ) -> dict[str, object]:
        return {
            "proposal_version_id": str(version.id),
            "proposal_content_hash": version.content_hash,
            "portfolio_input_hash": version.portfolio_input_hash,
            "portfolio_as_of": ProposalService._utc(version.portfolio_as_of).isoformat(),
            "analysis_id": str(analysis.id),
            "analysis_evidence_hash": analysis.evidence_hash,
            "risk_evaluation_id": str(analysis.risk_evaluation_id),
            "scenario_run_id": (
                None if analysis.scenario_run_id is None else str(analysis.scenario_run_id)
            ),
        }

    @staticmethod
    def _aware_required(value: datetime) -> None:
        if value.tzinfo is None:
            raise InvalidWorkflowTransition("workflow timestamps must be timezone-aware")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
