# ADR 0017: Fund-scoped authorization, separation of duties, and audit

## Context

Having three named roles is not a control unless every sensitive transition checks the actor, fund,
permission, and decision context. A role alone also does not prevent self-approval.

## Decision

Use the existing fund-scoped `user_roles` assignments as the authorization source:

- analysts create, revise, analyze, submit, and withdraw their own proposals;
- portfolio managers start review, record reviews, request changes, and approve or reject;
- faculty advisors record advisory reviews and request changes, but cannot make the final decision.

Inactive users have no authority. Ownership checks supplement role checks. The proposal author may
never approve or reject their own proposal, even if that user also holds the manager role.

Each workflow action appends both a typed proposal transition and a generic audit event. Final
decision provenance includes content and portfolio hashes, valuation cutoff, bound risk evaluation,
optional scenario run, and review count. PostgreSQL triggers prevent updates or deletes of policy,
proposal-version, analysis, review, transition, and audit evidence.

## Alternatives

- Check roles only in a future UI: bypassable by scripts or APIs.
- Allow advisors to approve: weakens the distinction between oversight and portfolio authority.
- Permit self-approval when a user has multiple roles: rejected for separation-of-duties risk.

## Consequences

Governance rules are enforced at the application-service boundary and durable evidence is protected
in PostgreSQL. Authentication and token issuance remain separate concerns; callers must supply an
authenticated user identity when API surfaces are added.
