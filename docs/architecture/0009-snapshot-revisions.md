# ADR 0009: Persist immutable, reproducible snapshot revisions

Status: Accepted

## Context

Point-in-time reconstruction is proven, but committee and reconciliation workflows need durable evidence. Late effective transactions may change historical state without making earlier calculations unauditable.

## Decision

Persist canonical portfolio states as immutable revisions. Reuse an unchanged current revision; supersede it when the ledger-derived canonical state changes. Verify an old revision by replaying its recorded transaction IDs. Keep reported balances independent and reconcile them without modifying ledger state.

## Alternatives

- Overwrite one snapshot per date: rejected because historical calculation evidence would be lost.
- Treat snapshots as editable balances: rejected because that creates a second source of truth.
- Reconcile by creating automatic corrections: rejected because discrepancies require review and preserved evidence.

## Consequences

Storage grows by revision, while every historical result remains explainable. Snapshot status may change from current to superseded; all economic content and child rows remain immutable.
