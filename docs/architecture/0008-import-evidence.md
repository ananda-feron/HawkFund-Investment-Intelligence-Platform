# ADR 0008: Preserve imports as immutable row-level evidence

Status: Accepted

## Context

Batch totals alone cannot explain where a transaction came from, why a row failed, or how a duplicate differed from the original.

## Decision

Store every CSV source row, its raw and normalized payloads, hashes, source locator, outcome, and links to its transaction or conflict. Use content hashes for batch idempotency and the accepted transaction identity for ledger idempotency. Final import evidence is immutable.

## Alternatives

- Store only posted transactions: rejected because rejected and conflicting evidence would disappear.
- Update existing transactions on repeated IDs: rejected because imports must not silently rewrite history.
- Fail the whole file on one invalid row: rejected because valid evidence can be accepted independently while errors remain visible.

## Consequences

Imports consume more storage but become explainable and auditable. Additional provider adapters must normalize into the same command and evidence contract.
