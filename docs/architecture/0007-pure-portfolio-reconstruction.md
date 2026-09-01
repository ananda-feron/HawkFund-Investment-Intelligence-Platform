# ADR 0007: Reconstruct portfolio state in a pure domain engine

Status: Accepted

## Context

Portfolio state must be reproducible from the authoritative ledger and testable independently of PostgreSQL, FastAPI, authentication, and external services. Persisting derived balances before the accounting behavior is proven would risk creating a second source of truth.

## Decision

Implement reconstruction as a pure function over immutable ledger-domain records, a fund scope, and a timezone-aware `as_of`. The engine sorts by effective time, recorded time, and UUID; uses `Decimal`; applies moving weighted-average cost; preserves unknown basis; and handles corrections as effective-dated inverse effects. It returns immutable state and canonical calculation metadata but persists nothing.

Transaction enums live in the ledger domain package rather than the SQLAlchemy model module so the engine has no persistence dependency.

## Alternatives

- Calculate holdings with aggregate SQL queries: rejected because ordered corrections and cost-basis transitions need explicit, testable domain behavior.
- Build reconstruction into API handlers: rejected because transport concerns would contaminate accounting logic.
- Persist holdings or snapshots immediately: deferred until pure point-in-time reconstruction is stable.
- Use binary floating point: rejected for accounting quantities and money.

## Consequences

Repositories must map persisted rows into immutable engine records. The engine can be tested entirely in memory and produces the same canonical result for shuffled input. Snapshot persistence, reconciliation, valuation, and APIs remain separate later layers.
