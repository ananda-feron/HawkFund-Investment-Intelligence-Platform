# Investment governance semantics

## Roles and permissions

| Capability | Analyst | Portfolio manager | Faculty advisor |
| --- | ---: | ---: | ---: |
| Create/revise own proposal | Yes | No | No |
| Bind risk analysis | Yes | Yes | No |
| Submit/withdraw own proposal | Yes | No | No |
| Start review | No | Yes | No |
| Record review | No | Yes | Yes |
| Request changes | No | Yes | Yes |
| Approve/reject | No | Yes | No |
| Read governance history | Yes | Yes | Yes |

All permissions are fund-scoped and inactive users are denied. Ownership and separation-of-duties
checks remain in force when a person has more than one role.

## Proposal evidence

Each immutable content version contains:

- title and investment thesis;
- exact portfolio cutoff and reconstruction input hash;
- one structured action per instrument;
- current and proposed weights, estimated notional, and rationale;
- a canonical content hash and link to the superseded version.

Actions must agree with their weights: buy increases, sell decreases without reaching zero, exit
reaches zero, and hold is unchanged. Proposal approval never posts a transaction.

Risk and optional scenario results attach through append-only analysis evidence. The binding hash
includes proposal content, portfolio input, risk-evaluation input, and scenario input. A new proposal
version has no inherited analysis.

## Policy controls

Policy rules are versioned and immutable. Severity is either `BLOCKING` or `WARNING`. Blocking
breaches and unavailable blocking metrics prevent submission and approval; warning outcomes remain
visible but do not stop the workflow.

Phase 5 provides policy-ready liquidity metrics:

- cash weight;
- portfolio weight liquid within a configured horizon;
- maximum days to liquidate when every position has valid average-daily-volume evidence.

Days to liquidate equals position market value divided by average daily traded value and the maximum
participation rate. Missing volume evidence is never replaced with an estimate: the maximum-days
metric becomes unavailable and a warning is emitted.

The deterministic base policy now includes maximum technology exposure, maximum position weight,
minimum cash weight, and minimum weight liquid within the horizon.

## Decision and audit history

Every state transition records actor, authorized role, prior and resulting status, proposal version,
reason, timestamp, resulting optimistic version, and decision provenance. The generic audit stream
references each typed transition. Rejection, withdrawal, and change requests require reasons.

Approved, rejected, and withdrawn proposals are terminal. Stale expected versions fail rather than
overwriting another committee member's action.

Out of scope: authentication/token issuance, API/UI workflow screens, notifications, e-signatures,
trade order generation, broker execution, and legal-compliance certification.
