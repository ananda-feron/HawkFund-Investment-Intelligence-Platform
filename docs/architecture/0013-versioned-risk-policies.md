# ADR 0013: Versioned policies and immutable breach evidence

## Context

A breach must explain which policy was effective, what metric was observed, what threshold applied,
and by how much it was exceeded. Mutable thresholds cannot support historical governance.

## Decision

Persist effective-dated, versioned policies and their rules. Rules address named metrics, apply a
maximum or minimum threshold, declare their unit, and carry an explanation template. Each evaluation
stores a canonical input hash and immutable item-level results: pass, breach, or unavailable.

The portfolio risk pipeline composes point-in-time valuation, effective-dated classifications,
exposure, risk statistics, named metrics, and the policy effective at the same cutoff.

## Alternatives

- Hard-code limits in application code: simple but unauditable and difficult to version.
- Store only active breaches: loses evidence that controls ran and passed.
- Treat unavailable metrics as passing: hides data-quality failures.

## Consequences

Threshold changes require a new policy version. Evaluation evidence consumes storage but can be
reproduced and explained. Missing metrics are visible as unavailable and never silently pass.
