# ADR 0011: Deterministic historical valuation

## Context

The platform must answer point-in-time questions such as "What was the fund worth on March 31?"
without using today's holdings or a price published after that cutoff.

## Decision

Historical valuation composes two independently deterministic inputs:

1. reconstruct the ledger through the requested timezone-aware cutoff;
2. select the latest eligible immutable price for each resulting position at that cutoff.

The pure valuation engine computes security market value as quantity multiplied by price, portfolio
value as cash plus securities, and unrealized P&L as market value less moving-average cost basis.
Trade realized P&L uses the same moving-average basis semantics as reconstruction. Unknown basis is
reported as unavailable rather than guessed. Missing prices fail valuation; stale prices remain
visible with warnings and provenance.

## Alternatives

- Persist daily valuation as the only source: fast to query, but insufficient for corrections and
  arbitrary cutoffs.
- Use current prices for historical holdings: produces hindsight-contaminated results.
- Substitute zero or last-known price without disclosure: yields plausible but misleading totals.

## Consequences

The MVP may replay ledger history and is not optimized for large portfolios. Results are auditable,
future prices cannot leak into past valuation, and later caching can be validated against the same
pure calculation.
