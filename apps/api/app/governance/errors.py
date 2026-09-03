class GovernanceError(ValueError):
    pass


class AuthorizationDenied(GovernanceError):
    pass


class InvalidWorkflowTransition(GovernanceError):
    pass


class ConcurrentProposalUpdate(GovernanceError):
    pass


class PolicyEvidenceRequired(GovernanceError):
    pass
