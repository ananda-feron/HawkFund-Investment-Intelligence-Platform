# ADR 0014: Non-mutating scenario projections

## Context

Stress testing asks what would happen under hypothetical conditions. Treating projected prices or
positions as accepted market data or portfolio state would contaminate the system of record.

## Decision

Apply scenarios only to an immutable point-in-time valuation in memory. Preserve baseline price and
quote provenance, compute projected prices and market values separately, and leave cash, quantities,
cost basis, ledger transactions, accepted prices, and portfolio snapshots unchanged.

Persist versioned scenario definitions and immutable execution evidence. The execution hash covers
the baseline valuation and quote observations, shocks, effective classifications and sensitivities,
portfolio and benchmark return histories, policy, confidence level, annualization, and comparison
settings. Repeating identical inputs returns the existing run.

## Alternatives

- Insert hypothetical prices into market data: reuses valuation code but pollutes accepted evidence.
- Create synthetic ledger transactions: useful for trade proposals, but incorrect for pure market
  stress and outside Phase 4.
- Persist only aggregate P&L: compact, but cannot explain instrument contributions.

## Consequences

Scenario output is clearly separated from authoritative state and can be reproduced. Position-level
evidence consumes additional storage. Trade-rebalancing scenarios remain deferred to the portfolio
decision phase.
