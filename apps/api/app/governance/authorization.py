from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.governance.errors import AuthorizationDenied
from app.governance.types import GovernanceRole, Permission
from app.models import Role, User, UserRole

ROLE_PERMISSIONS: dict[GovernanceRole, frozenset[Permission]] = {
    GovernanceRole.ANALYST: frozenset(
        {
            Permission.CREATE_PROPOSAL,
            Permission.REVISE_PROPOSAL,
            Permission.RECORD_ANALYSIS,
            Permission.SUBMIT_PROPOSAL,
            Permission.WITHDRAW_PROPOSAL,
            Permission.VIEW_GOVERNANCE,
            Permission.USE_AI_ASSISTANT,
        }
    ),
    GovernanceRole.MANAGER: frozenset(
        {
            Permission.RECORD_ANALYSIS,
            Permission.START_REVIEW,
            Permission.RECORD_REVIEW,
            Permission.REQUEST_CHANGES,
            Permission.APPROVE_PROPOSAL,
            Permission.REJECT_PROPOSAL,
            Permission.VIEW_GOVERNANCE,
            Permission.USE_AI_ASSISTANT,
        }
    ),
    GovernanceRole.ADVISOR: frozenset(
        {
            Permission.RECORD_REVIEW,
            Permission.REQUEST_CHANGES,
            Permission.VIEW_GOVERNANCE,
            Permission.USE_AI_ASSISTANT,
        }
    ),
}


class AuthorizationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def require(self, actor_user_id: UUID, fund_id: UUID, permission: Permission) -> GovernanceRole:
        user = self.session.get(User, actor_user_id)
        if user is None or not user.is_active:
            raise AuthorizationDenied("actor is missing or inactive")
        role_codes = self.session.scalars(
            select(Role.code)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == actor_user_id, UserRole.fund_id == fund_id)
        ).all()
        roles = tuple(
            GovernanceRole(code)
            for code in role_codes
            if code in {item.value for item in GovernanceRole}
        )
        authorized = sorted(
            (role for role in roles if permission in ROLE_PERMISSIONS[role]),
            key=lambda item: item.value,
        )
        if not authorized:
            raise AuthorizationDenied(f"actor lacks {permission.value} for fund {fund_id}")
        return authorized[0]
