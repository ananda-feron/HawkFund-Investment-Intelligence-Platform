# ADR 0010: Append-only market-data observations

## Context

Historical valuation must be reproducible even when a provider later restates a price. A mutable
"current price" table would erase the evidence used by an earlier calculation.

## Decision

Store provider observations as immutable rows keyed by instrument, provider, price type, and
observation timestamp. Resolve vendor symbols through effective-dated security identifiers. Track
each request in a market-data batch, retain source metadata, and record changed duplicate keys as
conflicts without replacing the accepted observation.

Price selection uses the latest observation at or before the valuation cutoff. Freshness is an
explicit comparison between the cutoff and observation timestamp using a caller-provided maximum
age. Receipt time is provenance, not the market timestamp.

## Alternatives

- Overwrite one current price per instrument: simpler, but destroys historical evidence.
- Bind the domain directly to one vendor SDK: faster initially, but leaks vendor identity and
  transport behavior into valuation.
- Automatically accept restatements: convenient, but makes prior results silently change.

## Consequences

Storage grows with history and conflicts require deliberate resolution. In return, vendor adapters
remain replaceable and every selected quote identifies its source row, provider, timestamps, and
metadata.
