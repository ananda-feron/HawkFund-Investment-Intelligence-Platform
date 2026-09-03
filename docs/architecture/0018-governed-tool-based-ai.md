# ADR 0018: Governed tool-based AI

## Context

A language model is useful for explaining portfolio state but is not a deterministic calculator or
a trusted authorization principal. Model-selected arguments, generated prose, and data retrieved
from external sources can all be adversarial or wrong.

## Decision

Expose six strict application tools: holdings, exposure, risk, portfolio snapshot, scenario preview,
and policy breaches. The application binds each call to an authenticated actor and fund, validates
the exact JSON shape, executes deterministic services, and independently attaches source records.
The scenario tool calls the non-persisting preview path. There are no mutation tools.

Require at least one successful tool result with source evidence before returning model prose. If
evidence is absent, denied, invalid, or unavailable, return a deterministic refusal. Repeat the
security instructions after tool calls and mark tool data as untrusted. Bound tool rounds and call
counts. Store response bodies at HawkFundOS, disable provider-side response storage, and use a hashed
actor identifier for provider safety controls.

Append user messages, assistant messages/refusals, tool arguments, statuses, results, hashes,
sources, and generic audit events. PostgreSQL triggers make messages and tool calls immutable and
permit only the terminal transition of a conversation.

## Alternatives

- Let the model calculate metrics: rejected because results would not be reproducible.
- Put a fund identifier in tool arguments: rejected because it permits confused-deputy scope changes.
- Give the model generic database or mutation tools: rejected because authorization and provenance
  would be too broad.
- Trust citations written in prose: rejected because attribution must be constructed from application
  evidence.

## Consequences

Answers may refuse when the deterministic platform has incomplete data. Adding a tool requires an
explicit schema, permission review, provenance contract, implementation, and adversarial tests.
Provider credentials and HTTP/UI integration remain deployment concerns rather than fixture data.
