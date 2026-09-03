import pytest

from app.governance.authorization import AuthorizationService
from app.governance.errors import AuthorizationDenied
from app.governance.types import GovernanceRole, Permission
from tests.conftest import FUND_ID
from tests.governance.factories import ADVISOR_ID, ANALYST_ID, MANAGER_ID, seed_roles


def test_three_role_permission_matrix(session) -> None:
    seed_roles(session)
    authorization = AuthorizationService(session)

    assert (
        authorization.require(ANALYST_ID, FUND_ID, Permission.CREATE_PROPOSAL)
        is GovernanceRole.ANALYST
    )
    assert (
        authorization.require(MANAGER_ID, FUND_ID, Permission.APPROVE_PROPOSAL)
        is GovernanceRole.MANAGER
    )
    assert (
        authorization.require(ADVISOR_ID, FUND_ID, Permission.RECORD_REVIEW)
        is GovernanceRole.ADVISOR
    )
    with pytest.raises(AuthorizationDenied):
        authorization.require(ANALYST_ID, FUND_ID, Permission.APPROVE_PROPOSAL)
    with pytest.raises(AuthorizationDenied):
        authorization.require(ADVISOR_ID, FUND_ID, Permission.APPROVE_PROPOSAL)
