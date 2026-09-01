# ADR 0002: PostgreSQL owns authoritative application data

Status: Accepted

## Context

The platform will eventually ingest market data, calculate snapshots, queue work, and generate files. Multiple storage systems can make ownership ambiguous.

## Decision

PostgreSQL is the system of record for structured application state. Redis contains only disposable queue/cache data. Object storage will hold documents and generated artifacts, referenced by PostgreSQL metadata. External provider responses are normalized through adapters before use.

## Alternatives

- Redis as a primary store: rejected because durable relational state and auditability are required.
- Separate time-series database in Phase 0: rejected because daily student-fund data does not justify it.
- Data warehouse: deferred until analytical volume establishes a need.

## Consequences

Backups and consistency center on PostgreSQL. Cache loss must not lose business state. Provider-specific schemas cannot leak into domain interfaces.
