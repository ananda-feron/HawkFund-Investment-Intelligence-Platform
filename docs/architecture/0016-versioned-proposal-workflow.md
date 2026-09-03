# ADR 0016: Versioned investment-proposal state machine

## Context

Investment decisions need reviewable evidence and controlled transitions. Mutable proposal content
would allow a thesis or target weight to change after analysis or approval, invalidating the record.

## Decision

Represent a proposal as a small mutable aggregate containing only current status, current content
version, and an optimistic row version. Store title, thesis, portfolio cutoff/hash, proposed position
changes, analysis bindings, reviews, and transitions as append-only evidence.

The allowed path is:

```text
DRAFT -> SUBMITTED -> UNDER_REVIEW -> APPROVED | REJECTED
  ^           |             |
  +-----------+-------------+-> CHANGES_REQUESTED -> new DRAFT version
```

Withdrawal is allowed before active review or a final decision. A revision always creates a new
content version and invalidates analysis attached to the superseded version. Submission and approval
require policy evaluation evidence for the exact current version and valuation cutoff, with no
blocking breach or unavailable blocking metric.

Every command supplies an expected row version. The update succeeds only if it matches, preventing a
reviewer from overwriting a concurrent decision.

## Alternatives

- Mutable proposal rows: simpler, but cannot prove what was analyzed or approved.
- Store a final PDF only: human-readable, but cannot enforce machine controls or query provenance.
- Automatically carry analysis into revisions: convenient, but unsafe because the decision inputs
  changed.

## Consequences

The complete approval history can be reconstructed and stale decisions fail explicitly. More rows
are stored and edits require a new version. Approved proposals remain decisions, not executable
transactions; trade execution is outside Phase 5.
