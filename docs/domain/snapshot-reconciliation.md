# Snapshot and Reconciliation Contract

Status: Accepted for Phase 1 Sprint 1.4

## Snapshot source and identity

A snapshot is derived only by passing ledger-domain records through the accepted pure portfolio engine at an explicit `as_of`. It stores the engine version, canonical input hash, canonical state, applied transaction IDs, and normalized cash/position rows.

Snapshots never replace transactions as the source of truth.

## Revisions

- Repeating an unchanged scope and cutoff reuses the current snapshot.
- A late or corrected transaction that changes the reconstruction creates the next revision.
- The prior revision becomes `SUPERSEDED`; its content remains immutable.
- Exactly one `CURRENT` revision exists per fund/account cutoff.
- Revisions link through `supersedes_snapshot_id`.

## Reproducibility

Verification replays the exact transaction IDs recorded by the snapshot, using the stored cutoff and engine version metadata, and compares both the canonical input hash and canonical state. Later transactions do not invalidate the reproducibility of an earlier revision.

## Reported evidence

Reported cash and position balances are independent observations with source identity, cutoff, account, optional instrument, recorded time, and evidence metadata. They never create or alter transactions.

## Reconciliation

For each observation:

```text
difference = reported value - snapshot-derived expected value
```

- `MATCHED`: absolute difference is within tolerance.
- `BREACH`: absolute difference exceeds tolerance.
- `UNAVAILABLE`: no applicable observations exist.

Runs and discrepancy items are idempotent for `(snapshot_id, tolerance, canonical evidence hash)`, immutable after creation, and audited. New evidence creates a new run rather than silently reusing an earlier result. Reconciliation never automatically corrects the ledger.
