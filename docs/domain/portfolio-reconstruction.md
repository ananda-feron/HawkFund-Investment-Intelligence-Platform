# Portfolio Reconstruction Contract

Status: Accepted for Phase 1 Sprint 2

## 1. Purpose and boundary

The portfolio engine deterministically derives accounting state from authoritative ledger facts. It answers how much USD cash and how many units of each instrument the fund owns at an `as_of` timestamp, together with accounting cost basis and calculation provenance.

The engine does not query PostgreSQL, call HTTP services, authenticate users, read files, obtain market prices, calculate market value or P&L, persist snapshots, or mutate ledger records.

## 2. Interface

```text
PortfolioEngine.reconstruct(
    fund_id,
    transactions,
    as_of,
    account_id=None,
) -> PortfolioState
```

Inputs are immutable normalized domain records. A repository may map SQLAlchemy rows into these records, but database access remains outside the engine.

The result contains:

- fund and optional account scope;
- aggregate USD cash and cash by account;
- positions identified by account and instrument;
- quantity, total cost basis, average cost, and cost-basis status;
- `as_of`, engine version, canonical input hash, transaction count, ordered transaction IDs, and last applied transaction ID.

## 3. Inclusion and ordering

- Every supplied transaction must belong to `fund_id`; mixed-fund input is rejected.
- When `account_id` is supplied, only that account's transactions are included.
- A transaction is included exactly when `effective_at <= as_of`.
- `as_of`, `effective_at`, and `recorded_at` must be timezone-aware.
- Included transactions are sorted by `effective_at`, then `recorded_at`, then UUID.
- Input collection order has no effect on output.
- The mutable convenience status on an original transaction is not used to exclude it. A reversal takes effect only when its own ordered record is included.

## 4. Cash effects

```text
OPENING_CASH       + amount
CASH_DEPOSIT       + amount
CASH_WITHDRAWAL    - amount
BUY                - quantity × unit price - fees
SELL               + quantity × unit price - fees
DIVIDEND           + amount
FEE                - amount
OPENING_POSITION     no effect
REVERSAL             exact inverse of target cash effect
```

Cash uses `Decimal` without intermediate rounding. Negative cash is retained in the result and produces a `NEGATIVE_CASH` warning; it is not a reconstruction failure.

## 5. Quantity and moving weighted-average cost

`BUY` adds quantity and capitalizes gross purchase cost plus trade fees. If the existing position has known basis:

```text
new total basis = old total basis + quantity × unit price + fees
new average cost = new total basis / new quantity
```

`SELL` removes quantity at the average cost immediately before the sale:

```text
basis removed = sold quantity × prior average cost
remaining total basis = prior total basis - basis removed
```

Sale proceeds and sale fees affect cash, not the remaining position's cost basis. Selling more than the available quantity fails reconstruction. A completely liquidated position is omitted from output.

Positions remain separated by account and instrument. Aggregate cash is the sum of account cash balances.

## 6. Opening positions and unknown basis

`OPENING_POSITION` adds quantity without affecting cash.

- With a unit price, initial basis is `quantity × unit_price` and status is `KNOWN`.
- Without a unit price, basis and average cost are `None` and status is `UNKNOWN`.
- Later known purchases do not make an unknown mixed position known.
- Sales from an unknown-basis position preserve `UNKNOWN` until complete liquidation.
- Unknown is never represented as zero.

## 7. Reversals

During replay, the engine records the actual cash, quantity, and cost-basis effect produced by each non-reversal transaction. A `REVERSAL` applies the exact inverse of that recorded effect at the reversal's own ordered time.

- The target must already have been applied in the reconstruction order.
- A reversal cannot target another reversal.
- A target can be reversed at most once.
- The reversal and target must share fund and account.
- Applying an inverse that would create a negative holding or negative known cost basis fails reconstruction.
- A reversal after `as_of` has no effect at that cutoff.
- A replacement is an ordinary later transaction and applies only when included by `as_of`.

This defines correction behavior as an effective-dated compensating event. It does not rewrite earlier historical state.

## 8. Determinism and canonical metadata

The engine version is a constant included in every result. The canonical input hash covers the ordered, included economic fields and excludes mutable persistence projections such as transaction status.

For the same fund/account scope, transaction facts, `as_of`, and engine version, the canonical serialized result must be byte-equivalent regardless of input order or process run.

## 9. Required failures and warnings

Reconstruction fails with a typed domain error for:

- naive timestamps;
- mixed-fund input;
- unsupported transaction types or malformed required fields;
- overselling or any other negative holding transition;
- reversal target absent from the included ordered history;
- reversal of a reversal or repeated reversal;
- reversal across fund/account scope;
- negative known position cost basis.

Reconstruction succeeds with warnings for:

- negative account cash;
- unknown position cost basis.

## 10. Persistence boundary

`PortfolioState` is returned in memory only. Sprint 2 adds no snapshot tables or writes derived balances to PostgreSQL. Durable snapshots and reconciliation remain later work after reconstruction behavior is proven.
