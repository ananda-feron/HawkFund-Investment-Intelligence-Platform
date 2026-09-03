# AI intelligence boundary

Phase 6 is an explanation layer, not another financial engine.

## Request path

```text
authenticated actor + fund
        -> USE_AI_ASSISTANT authorization
        -> strict read-only tool registry
        -> deterministic application service
        -> result + warnings + source records
        -> model explanation
        -> application-attached citations and immutable audit evidence
```

The model can request `get_holdings`, `get_exposure`, `get_risk`,
`get_portfolio_snapshot`, `run_scenario`, and `get_policy_breaches`. Tool arguments never contain a
fund ID. `run_scenario` previews a versioned definition and does not create a scenario run.

## Grounding and refusal

An answer is grounded only when a successful tool produces at least one application source and the
provider returns non-empty prose. Source references include record type, stable record ID, label,
as-of time where applicable, and deterministic input hash where available. The application—not the
model—deduplicates and attaches them. Without source evidence, the stored and returned response is a
fixed refusal.

## Security and audit

- Existing fund-scoped analyst, manager, and advisor roles receive the read-only assistant permission.
- Unknown tools, extra arguments, malformed timestamps, and attempted fund overrides are rejected.
- Tool data is labeled untrusted, and system instructions are repeated on every provider turn.
- Tool loops are bounded to four rounds and eight calls by default.
- Provider-side response storage is disabled; a one-way actor hash is used as the safety identifier.
- Conversations, messages, citations, tool calls, results, hashes, errors, and audit events are stored.
- PostgreSQL protects messages and tool-call evidence from update or deletion.

The implementation intentionally provides an injected provider adapter and no repository secret.
Production wiring must obtain credentials from a secret manager and authenticate the caller before
constructing the application context.
