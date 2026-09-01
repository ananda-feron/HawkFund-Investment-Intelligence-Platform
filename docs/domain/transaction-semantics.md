# Transaction Domain Semantics

Status: Proposed Phase 1 contract  
Scope: Long-only, single-currency portfolio ledger  
Base currency: USD  

## 1. Purpose

This document defines the accounting contract for HawkFundOS Phase 1. Given the same ordered set of valid ledger transactions, the portfolio engine must always reconstruct the same holdings and cash at any requested point in time.

Transactions are observed, append-only facts. Holdings, cash balances, cost basis, and portfolio snapshots are derived values. A derived value must never replace or silently modify the transaction history that produced it.

Phase 1 does not include market prices, valuation, P&L, performance, risk, scenarios, trade execution, or AI behavior.

## 2. Domain boundary

### Observed facts

- A fund and account exist.
- An instrument exists in the security master.
- A transaction was entered directly or received from an identified source.
- The source supplied an external identifier and source values.
- A correction reverses a specific prior transaction.
- A reported balance was supplied for reconciliation.

### Derived state

- Current or point-in-time instrument quantity.
- Current or point-in-time cash balance.
- Position cost basis.
- Portfolio snapshots.
- Reconciliation differences.
- Realized or unrealized gain/loss.

Derived state is reproducible and disposable. Deleting and rebuilding all snapshots must not change the transaction ledger.

## 3. Entity responsibilities

### Fund

Defines the managed legal/organizational portfolio boundary, base currency, and timezone. The Phase 0 `funds` record remains authoritative.

### Instrument

Identifies a tradable security. The Phase 0 `instruments` record remains authoritative. Cash is not represented as a synthetic instrument in Phase 1.

### Account

Defines a ledger boundary within a fund, such as the primary brokerage account. Every transaction belongs to exactly one account. Phase 1 supports USD accounts only, while retaining a currency field for validation and future expansion.

### Transaction

An immutable, normalized ledger fact. Direction is expressed by transaction type; numeric magnitudes are stored as non-negative values. A posted transaction is never edited in place.

### ImportBatch

Captures one attempt to import records from an external source, including source identity, file checksum, status, timestamps, and row counts. It provides provenance but does not determine accounting behavior.

### Opening balance

An explicit ledger fact establishing initial cash or position quantity at the migration boundary. It is not a mutable field on an account or holding.

### Correction

An append-only reversal of a specific posted transaction, optionally followed by a replacement transaction. Correction is a relationship and workflow, not an unconstrained signed adjustment.

### PortfolioSnapshot

A dated, derived representation of holdings and cash produced from ledger history at a declared cutoff and calculation version. It is never the source of truth.

### ReportedBalance

An independently observed cash or position balance used for reconciliation. It must remain separate from ledger-derived state and must never automatically change the ledger.

## 4. Supported transaction types

Phase 1 supports the smallest set needed to reconstruct a long-only cash equity portfolio.

| Type | Instrument required | Quantity required | Unit price required | Amount required | Holding effect | Cash effect |
|---|---:|---:|---:|---:|---|---|
| `BUY` | Yes | Yes | Yes | No | `+quantity` | `-(quantity × unit_price) - fees` |
| `SELL` | Yes | Yes | Yes | No | `-quantity` | `+(quantity × unit_price) - fees` |
| `CASH_DEPOSIT` | No | No | No | Yes | None | `+amount` |
| `CASH_WITHDRAWAL` | No | No | No | Yes | None | `-amount` |
| `DIVIDEND` | Yes | No | No | Yes | None | `+amount` |
| `FEE` | Optional | No | No | Yes | None | `-amount` |
| `OPENING_CASH` | No | No | No | Yes | None | `+amount` |
| `OPENING_POSITION` | Yes | Yes | Optional | No | `+quantity` | None |
| `REVERSAL` | Inherited | Inherited | Inherited | Inherited | Exact inverse of target | Exact inverse of target |

`fees` is permitted only on `BUY` and `SELL`. A standalone charge uses `FEE`. All quantities, prices, amounts, and fees are stored as non-negative magnitudes. Zero is rejected wherever a field is required.

### Deferred types

The following are intentionally excluded until their accounting rules are specified and tested:

- stock splits and reverse splits;
- transfers between accounts;
- return of capital;
- interest;
- taxes and withholding;
- mergers, spin-offs, and symbol changes;
- short sales, covering transactions, margin, and derivatives;
- foreign exchange and non-USD settlement.

Unsupported records must fail validation or be quarantined during import. They must not be approximated as a supported type.

## 5. Transaction record

### Required for every transaction

| Field | Meaning |
|---|---|
| `id` | Internal UUID assigned once |
| `fund_id` | Owning fund |
| `account_id` | Account affected by the transaction |
| `transaction_type` | One supported type |
| `effective_at` | UTC instant at which the transaction affects derived state |
| `recorded_at` | UTC instant at which HawkFundOS accepted the fact |
| `currency` | ISO 4217 currency; must be `USD` in Phase 1 |
| `source` | Controlled source code such as `manual`, `phase1_fixture`, or `hawkfund_csv` |
| `external_id` | Stable identity within the source namespace |
| `status` | `POSTED` or `REVERSED`; draft/import staging rows are not ledger transactions |

### Conditionally required

| Field | Rule |
|---|---|
| `instrument_id` | Required for `BUY`, `SELL`, `DIVIDEND`, and `OPENING_POSITION` |
| `quantity` | Required for `BUY`, `SELL`, and `OPENING_POSITION` |
| `unit_price` | Required for `BUY` and `SELL`; optional for `OPENING_POSITION` |
| `amount` | Required for cash deposit/withdrawal, dividend, fee, and opening cash |
| `fees` | Optional for `BUY` and `SELL`; defaults to zero |
| `reverses_transaction_id` | Required for `REVERSAL`; forbidden for every other type |
| `import_batch_id` | Required for imported records; absent for manual records |

### Optional descriptive fields

- `trade_date`: source-local calendar date for a trade when supplied;
- `settlement_date`: source-local settlement date when supplied;
- `description`: short source or operator description;
- `source_metadata`: provider-specific JSON retained for provenance, never interpreted as authoritative accounting logic;
- `created_by_user_id`: required for manually entered records.

### Fields not stored on the transaction

The normalized ledger does not store current holdings, current cash, portfolio weight, market value, realized P&L, or unrealized P&L. Gross trade value (`quantity × unit_price`) and net cash effect are computed from normalized fields.

If an import supplies a gross or net amount, retain it as source evidence and validate it against the normalized calculation. Do not substitute an inconsistent source total silently.

## 6. Numeric conventions

- Use PostgreSQL `NUMERIC`, Python `Decimal`, and serialized decimal strings for accounting values.
- Never use binary floating point for quantities, prices, fees, cash, or cost basis.
- Quantity precision: up to 12 decimal places.
- Price precision: up to 8 decimal places.
- Monetary precision: up to 4 decimal places internally; display rounding is separate.
- Required numeric magnitudes must be greater than zero.
- Optional `fees` may be zero but never negative.
- Transaction type, not numeric sign, determines direction.
- Round only at an explicitly documented accounting boundary; do not round after every intermediate operation.

## 7. Effective time and deterministic ordering

`effective_at` controls point-in-time state. `recorded_at` controls audit chronology but never changes historical accounting order.

Transactions are applied in this total order:

1. `effective_at` ascending;
2. `recorded_at` ascending;
3. `id` ascending.

The UUID tie-breaker makes replay deterministic when source events share timestamps. An import must normalize effective timestamps before posting. Phase 1 does not infer order from database insertion order.

A point-in-time query with cutoff `T` includes posted transactions where `effective_at <= T`, including qualifying reversals. A transaction recorded after `T` but effective before `T` changes a subsequently rebuilt historical snapshot; snapshot metadata must expose its build time and ledger watermark.

## 8. Cash, holding, and cost-basis effects

### BUY

- Holding quantity increases by `quantity`.
- Cash decreases by `quantity × unit_price + fees`.
- Position total cost basis increases by the same cash outflow.

### SELL

- Holding quantity decreases by `quantity`.
- Cash increases by `quantity × unit_price - fees`.
- Phase 1 uses moving weighted-average cost for long positions.
- Cost basis removed is `quantity × average_cost_before_sale`.
- Sale fees reduce realized proceeds; they do not change the remaining position's average cost.
- A sell that would make quantity negative is rejected.

### CASH_DEPOSIT and CASH_WITHDRAWAL

- Affect cash only.
- They are external flows and have no instrument or cost basis.
- Phase 1 permits negative cash because a valid trade/import ordering may temporarily create it; negative cash is surfaced as a reconciliation/control warning rather than silently rejected.

### DIVIDEND

- Increases cash by `amount`.
- Requires an instrument for provenance.
- Does not change position quantity or cost basis.
- A dividend may be recorded after the position has been sold if the effective date and source support it.

### FEE

- Decreases cash by `amount`.
- Does not change quantity or position cost basis.
- An optional instrument link attributes the fee without changing accounting behavior.

### OPENING_CASH

- Increases cash by `amount` at the migration boundary.
- Each account may have at most one active opening-cash transaction.
- It must be the earliest cash-affecting fact for that account.

### OPENING_POSITION

- Increases holding quantity without affecting cash.
- Each account/instrument pair may have at most one active opening-position transaction.
- It must be the earliest quantity-affecting fact for that account/instrument.
- If `unit_price` is present, initial total cost basis is `quantity × unit_price`.
- If `unit_price` is absent, quantity remains reproducible but cost basis is `UNKNOWN`; it must not be represented as zero.

### REVERSAL

- Produces the exact inverse cash, quantity, and cost-basis effect of one target transaction.
- A target may be reversed only once.
- A reversal must use the same fund and account as its target.
- The target remains immutable and queryable; its status becomes `REVERSED` only as a convenient projection of the reversal relationship.
- A reversal cannot target another reversal.
- The reversal's `effective_at` is explicit. It does not silently rewrite the target's original effective time.

## 9. Correction workflow

There is no generic `CORRECTION` transaction carrying arbitrary deltas.

To correct a posted transaction:

1. Append a `REVERSAL` referencing the incorrect transaction.
2. If necessary, append a new correctly normalized transaction.
3. Link both operations through audit metadata or a correction command identifier.

Example:

```text
Original:    BUY 100 AAPL @ 200.00, effective 2026-01-10
Correction:  REVERSAL of original, effective 2026-01-12
Replacement: BUY 10 AAPL @ 200.00, effective 2026-01-12
```

The portfolio contains 100 shares through January 11 and 10 shares from January 12 onward. If source evidence proves the original historical fact never occurred, an authorized restatement workflow may use the original effective time, but it must still append reversal/replacement facts and rebuild affected snapshots. That workflow is deferred until its authorization policy is defined.

## 10. Idempotency

### Imported transactions

The canonical idempotency key is:

```text
(fund_id, source, external_id)
```

It is enforced with a unique database constraint. Reimporting the same source record returns the existing transaction and does not add another ledger effect.

If the same key arrives with different normalized accounting fields:

- do not overwrite the existing transaction;
- mark the import row as `CONFLICT`;
- record the differing fields and both payload hashes;
- require an explicit correction workflow.

### Manual transactions

Manual create commands require a client-generated idempotency key. Retrying the same request with the same key and same normalized payload returns the original result. Reusing the key with a different payload is a conflict.

### Import batches

An import file checksum prevents accidental reprocessing at the batch level, while transaction-level keys remain the final deduplication control. Two different files may legitimately contain the same transaction records.

## 11. Import lifecycle and provenance

Import rows pass through:

```text
RECEIVED -> NORMALIZED -> VALIDATED -> POSTED
                                 |-> REJECTED
                                 |-> DUPLICATE
                                 |-> CONFLICT
```

Only `POSTED` transactions affect the ledger. A batch stores:

- source code;
- original filename when applicable;
- SHA-256 file/content checksum;
- received and completed timestamps;
- initiating user or service identity;
- total, posted, duplicate, rejected, and conflict counts;
- parser/schema version;
- failure summary.

Each imported transaction links to its batch and retains its external identifier, normalized payload hash, and source row number or equivalent locator. Raw input is treated as evidence, not as executable instructions.

## 12. Validation rules

### Referential and scope validation

- Fund, account, instrument, user, batch, and reversal target must exist when referenced.
- Account must belong to the transaction's fund.
- Referenced instrument must be active or explicitly permitted for historical import.
- Imported batch must use the same fund and source as the transaction.

### Field-shape validation

- Fields required by the transaction-type matrix must be present.
- Fields forbidden by the matrix must be absent.
- Currency must be USD in Phase 1.
- Effective and recorded timestamps must include timezone information.
- External ID and source must be non-empty after normalization.
- Description and metadata have explicit size limits.

### Accounting validation

- Numeric magnitudes must satisfy the precision and positivity rules.
- Trade gross value and net cash effect must be calculable without overflow.
- A sell cannot exceed the derived available quantity immediately before it in ledger order.
- A reversal must leave the replayed ledger valid; it cannot create an impossible negative holding at its effective position in the sequence.
- Required opening facts must precede ordinary activity in their ledger scope.
- Unknown opening-position cost basis remains unknown until an explicit supported adjustment exists.

Validation is performed both at the application boundary and through database constraints where practical. Database constraints protect shape and uniqueness; the deterministic engine protects time-dependent accounting invariants.

## 13. Portfolio engine contract

The pure engine accepts:

```text
derive_portfolio_state(
    ordered_transactions,
    cutoff,
    calculation_version
) -> PortfolioState
```

It does not query PostgreSQL, read CSV files, call APIs, use current time, or mutate its input. Repositories and import adapters normalize data before invoking it.

The result contains:

- fund and account identifiers;
- cutoff timestamp;
- cash by account/currency;
- quantity and cost-basis state by account/instrument;
- last applied transaction identifier and ledger watermark;
- calculation version;
- warnings such as unknown cost basis or negative cash.

The same normalized inputs, cutoff, and calculation version must produce byte-equivalent canonical output.

## 14. Required invariants

Automated tests must prove:

### Holding conservation

```text
ending quantity
= opening position
+ buys
- sells
+ exact reversal effects
```

### Cash conservation

```text
ending cash
= opening cash
+ deposits
- withdrawals
- buy gross values
- buy fees
+ sell gross values
- sell fees
+ dividends
- standalone fees
+ exact reversal effects
```

### Long-only constraint

Quantity for every account/instrument is never negative at any point in replay order.

### Idempotency

Posting or importing the same idempotency identity twice creates one ledger effect.

### Reproducibility

Replaying identical normalized history produces identical state and snapshot content.

### Point-in-time isolation

Transactions effective after a cutoff do not affect state at that cutoff.

### Reversal integrity

A transaction is reversed at most once, and target plus reversal have zero net effect from the reversal effective time onward.

### Referential integrity

No posted transaction references an unknown or cross-fund account, instrument, batch, user, or reversal target.

### Snapshot equivalence

A stored snapshot matches a fresh replay at the same cutoff, ledger watermark, and calculation version.

## 15. Snapshot semantics

Snapshots are created only after a successful ledger replay. A snapshot records:

- fund and optional account scope;
- cutoff timestamp;
- build timestamp;
- calculation version;
- ledger watermark and transaction count;
- canonical input hash;
- derived cash and position rows;
- warnings and reconciliation status.

Snapshots are immutable. If late or corrected transactions affect a prior cutoff, create a new snapshot revision rather than editing the prior snapshot. The latest valid revision may be selected for reads, while earlier revisions remain auditable.

## 16. Reconciliation semantics

Reported balances are independent observations with source, effective time, import batch or user, and evidence metadata.

For a reported value at cutoff `T`:

```text
difference = reported value - ledger-derived value
```

Reconciliation status is:

- `MATCHED` when the absolute difference is within the configured tolerance;
- `BREACH` when outside tolerance;
- `UNAVAILABLE` when ledger state or reported evidence is incomplete.

A breach records expected, reported, difference, tolerance, source, cutoff, and calculation version. It does not create a transaction or adjust a balance automatically.

## 17. Audit requirements

The system must preserve who or what performed each material action and when:

- import batch received/completed;
- transaction posted;
- duplicate, rejection, or conflict detected;
- reversal and replacement recorded;
- snapshot generated or superseded;
- reconciliation observation loaded and breach evaluated.

Audit events are append-only. They may summarize before/after references but do not replace the normalized ledger or raw source evidence.

## 18. Minimal Phase 1 read surface

Only after the engine and invariants pass tests, expose:

```text
GET /api/v1/funds/{fund_id}/transactions
GET /api/v1/funds/{fund_id}/holdings?as_of=<timestamp>
GET /api/v1/funds/{fund_id}/cash?as_of=<timestamp>
GET /api/v1/funds/{fund_id}/snapshots/{snapshot_date}
GET /api/v1/funds/{fund_id}/reconciliation?as_of=<timestamp>
```

Mutation commands for direct entry, import, and correction must be designed separately around idempotency and authorization. No dashboard is required to prove the Phase 1 accounting contract.

## 19. Required test scenarios before schema implementation is accepted

1. Opening cash, two buys, one sell, dividend, fee, and withdrawal reconcile to hand-calculated cash and quantity.
2. Selling more than the available quantity is rejected at the correct event.
3. Two events with the same effective timestamp replay deterministically.
4. Transactions after a point-in-time cutoff are excluded.
5. Reimporting an identical file and identical external IDs creates no new ledger effects.
6. Reusing an external ID with changed economics produces a conflict, not an update.
7. A reversal neutralizes exactly one target from its effective time onward.
8. Reversing twice or reversing a reversal is rejected.
9. Correcting a transaction retains the original, reversal, and replacement provenance.
10. Unknown opening cost basis remains unknown and never becomes zero implicitly.
11. Rebuilding a snapshot produces the same canonical content hash.
12. A reported balance mismatch creates a reconciliation breach without altering the ledger.

## 20. Implementation gate

Before creating the Phase 1 SQLAlchemy models or Alembic migration:

- review and accept this transaction-type matrix;
- confirm moving weighted-average cost as the Phase 1 cost-basis convention;
- confirm effective-time and tie-break ordering;
- confirm reversal-based correction semantics;
- confirm that negative holdings are blocked while negative cash is warned;
- confirm the import idempotency namespace;
- convert the required test scenarios into named test cases.

Until those decisions are accepted, the database schema and domain engine remain intentionally unimplemented.
