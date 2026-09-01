# ADR 0004: Financial calculations must be deterministic and versioned

Status: Accepted for later phases; no calculations are implemented in Phase 0

## Context

Portfolio and risk numbers must be reproducible for committee review, tests, and interview demonstrations. Results can change when inputs, conventions, or algorithms change.

## Decision

Application code—not the user interface or an AI model—will calculate financial metrics. Each persisted calculation will identify its inputs, as-of date, parameters, and methodology version. Golden datasets and reconciliation invariants will verify critical formulas.

## Alternatives

- Calculate in frontend components: rejected because behavior would be duplicated and difficult to audit.
- Use generative AI for numeric analysis: rejected because outputs are not a deterministic system of record.
- Persist results without methodology metadata: rejected because historical reproduction would be unreliable.

## Consequences

Methodology changes require versioning and migration planning. Calculations may be recomputed, and displayed values must carry freshness and methodology context.
