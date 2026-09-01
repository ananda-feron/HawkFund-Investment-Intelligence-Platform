# Market data and valuation semantics

## Price evidence

- `observed_at` is when the price applies; `received_at` is when HawkFundOS received it.
- All Phase 2 prices and valuations are USD.
- Provider observations are append-only. A changed duplicate creates conflict evidence and does not
  overwrite the accepted row.
- A quote must have `observed_at <= valuation as_of`. The newest qualifying timestamp wins.
- Freshness is deterministic: `as_of - observed_at > max_price_age` is stale. The caller supplies
  the policy duration; stale quotes are included with warnings, while missing quotes fail.
- Security identifiers may be provider-specific and effective-dated. Ticker is reference data, not
  assumed to be a permanent universal identity.

## Valuation formulas

For each reconstructed position:

```text
position market value = quantity × selected price
position unrealized P&L = market value − remaining moving-average cost basis
securities value = sum(position market values)
portfolio value = reconstructed cash + securities value
```

Realized trade P&L is net sale proceeds minus moving-average basis removed. Buy and sell fees are
already incorporated by the Phase 1 cost-basis rules. Reversing a sale reverses its realized P&L.
Dividends and standalone fees affect cash but are not classified as realized trade P&L. If a sale's
basis is unknown, aggregate realized P&L is unavailable rather than partially stated.

## Historical query contract

`HistoricalValuationService.value_at` reconstructs posted ledger entries through the exact
timezone-aware cutoff, selects only eligible prices, and returns quote provenance with every
position. No valuation rows are persisted in Phase 2; the result is a reproducible calculation.

Out of scope: live vendor credentials, FX, corporate actions, intraday bars, API/UI surfaces, risk,
scenarios, and AI.
