# ADR 0003: Transactions will be the portfolio system of record

Status: Accepted for Phase 1; no portfolio tables are implemented in Phase 0

## Context

Future holdings can be stored as editable current rows or derived from durable economic events. Editable holdings are simpler initially but cannot explain how a portfolio reached its current state.

## Decision

In Phase 1, transactions will be durable history and holdings will be reproducible, dated snapshots. Imported opening balances may seed the history. Every valuation will declare an as-of date and data freshness.

## Alternatives

- Store only current holdings: rejected because reconciliation and audit history would be weak.
- Full double-entry investment accounting in the first release: rejected as disproportionate to the educational MVP.

## Consequences

Snapshot logic must be deterministic and tested. Corrections require explicit events or controlled restatement rather than silent edits. Phase 0 intentionally creates no transaction, holding, or snapshot schema.
