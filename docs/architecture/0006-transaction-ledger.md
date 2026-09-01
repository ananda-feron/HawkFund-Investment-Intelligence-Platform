# ADR 0006: Use an append-only, idempotent transaction ledger

Status: Accepted

## Context

Phase 1 must reconstruct fund holdings and cash from observed history while preserving corrections, imports, and source evidence. Editable current balances cannot provide that audit trail.

## Decision

Transactions are immutable economic facts ordered by `effective_at`, `recorded_at`, and UUID. Moving weighted-average cost will be used when portfolio reconstruction is implemented. Negative holdings are prohibited; negative cash is permitted with a warning. Corrections append an exact reversal and optional replacement. Import identity is `(fund_id, source, external_id)`; identical content is idempotent and changed content is a conflict. Unknown opening cost basis remains unknown.

## Alternatives

- Editable holdings and cash: rejected because state would not be reproducible.
- In-place transaction corrections: rejected because original evidence would be lost.
- Treat changed duplicate content as an update: rejected because imports could silently rewrite history.
- Treat missing opening cost as zero: rejected because missing information is not an economic value.
- FIFO tax lots in Phase 1: deferred because moving weighted average is sufficient for the initial long-only fund ledger.

## Consequences

The database needs uniqueness, field-shape, opening-balance, and reversal constraints. Application services must detect duplicate-content conflicts before insertion. Portfolio state remains derived and is not implemented in Sprint 1.
