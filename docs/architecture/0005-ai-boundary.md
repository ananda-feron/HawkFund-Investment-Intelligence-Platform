# ADR 0005: AI remains a read-only explanatory boundary

Status: Implemented in Phase 6

## Context

An assistant can help analysts query portfolio and research data, but it creates hallucination, prompt-injection, privacy, and authorization risks.

## Decision

The assistant accesses HawkFundOS through typed, authorized, read-only tools. It explains
deterministic application results and the application attaches citations to underlying records. It
does not receive direct SQL access, calculate official financial metrics, modify portfolio data,
approve proposals, or execute trades.

## Alternatives

- Generic chatbot with portfolio data copied into prompts: rejected because grounding and access control would be weak.
- Autonomous write-capable agent: rejected because the educational decision workflow requires accountable human actions.
- No assistant: retained as a fallback if deterministic product features are incomplete.

## Consequences

Assistant tools reuse normal authorization, answers require citations and as-of context, and tests
cover groundedness, scope overrides, unavailable evidence, and prompt/tool injection.
