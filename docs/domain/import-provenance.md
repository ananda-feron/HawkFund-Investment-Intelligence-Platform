# Import and Provenance Contract

Status: Accepted for Phase 1 Sprint 1.3

## Pipeline

```text
CSV bytes -> batch identity -> parse -> normalize -> validate
          -> transaction idempotency -> ledger or conflict evidence
```

The supported Sprint 1.3 adapter is CSV. Provider-specific input is normalized into the existing `CreateTransaction` command; the transaction service remains the only ledger-writing authority.

## Batch identity

A batch is identified by `(fund_id, source, SHA-256 content hash)`. Reimporting identical bytes returns the completed batch without creating new row evidence or ledger effects. A different file may repeat transactions; transaction identity remains `(fund_id, source, external_id)`.

## Row lifecycle

Each source row is preserved with its row number, source locator, raw payload, raw hash, normalized payload when available, outcome, and error evidence.

```text
RECEIVED -> NORMALIZED -> POSTED
                       -> DUPLICATE
                       -> CONFLICT
RECEIVED/NORMALIZED    -> REJECTED
```

Invalid rows do not block valid rows in the same batch. Final row evidence is immutable.

## Conflict behavior

- Same transaction identity and same normalized economics: `DUPLICATE`.
- Same identity and different normalized economics: `CONFLICT`.
- A conflict links the incoming row, incoming hash/payload, original transaction, and import batch.
- The original transaction is never updated.

## Provenance

For every imported or duplicate transaction occurrence, the system can return:

- source and external identifier;
- batch and content hash;
- filename and source row;
- received timestamp;
- raw and normalized payload;
- posting outcome.

Raw input is evidence, not executable instructions. Import completion creates an append-only audit event.
