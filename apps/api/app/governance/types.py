from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID


class GovernanceRole(str, Enum):
    ANALYST = "analyst"
    MANAGER = "manager"
    ADVISOR = "advisor"


class Permission(str, Enum):
    CREATE_PROPOSAL = "CREATE_PROPOSAL"
    REVISE_PROPOSAL = "REVISE_PROPOSAL"
    RECORD_ANALYSIS = "RECORD_ANALYSIS"
    SUBMIT_PROPOSAL = "SUBMIT_PROPOSAL"
    START_REVIEW = "START_REVIEW"
    RECORD_REVIEW = "RECORD_REVIEW"
    REQUEST_CHANGES = "REQUEST_CHANGES"
    APPROVE_PROPOSAL = "APPROVE_PROPOSAL"
    REJECT_PROPOSAL = "REJECT_PROPOSAL"
    WITHDRAW_PROPOSAL = "WITHDRAW_PROPOSAL"
    VIEW_GOVERNANCE = "VIEW_GOVERNANCE"


class ProposalStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ProposalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"


class ReviewRecommendation(str, Enum):
    SUPPORT = "SUPPORT"
    OPPOSE = "OPPOSE"
    COMMENT = "COMMENT"


class WorkflowAction(str, Enum):
    CREATED = "CREATED"
    REVISED = "REVISED"
    ANALYZED = "ANALYZED"
    SUBMITTED = "SUBMITTED"
    REVIEW_STARTED = "REVIEW_STARTED"
    REVIEW_RECORDED = "REVIEW_RECORDED"
    CHANGES_REQUESTED = "CHANGES_REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True, slots=True)
class ProposalLineInput:
    instrument_id: UUID
    action: ProposalAction
    current_weight: Decimal
    proposed_weight: Decimal
    estimated_notional: Decimal
    rationale: str


@dataclass(frozen=True, slots=True)
class ProposalVersionInput:
    title: str
    thesis: str
    portfolio_input_hash: str
    portfolio_as_of: datetime
    lines: tuple[ProposalLineInput, ...]
