# ADR 0005: AI remains a read-only explanatory boundary

Status: Accepted for a later phase; no AI dependencies or code are implemented in Phase 0

## Context

An assistant can help analysts query portfolio and research data, but it creates hallucination, prompt-injection, privacy, and authorization risks.

## Decision

The future assistant will access HawkFundOS through typed, authorized, read-only tools. It will explain deterministic application results and cite underlying records. It will not receive direct SQL access, calculate official financial metrics, modify portfolio data, approve proposals, or execute trades.

## Alternatives

- Generic chatbot with portfolio data copied into prompts: rejected because grounding and access control would be weak.
- Autonomous write-capable agent: rejected because the educational decision workflow requires accountable human actions.
- No assistant: retained as a fallback if deterministic product features are incomplete.

## Consequences

Assistant tools must reuse normal authorization, answers require citations and as-of context, and evaluation must cover groundedness and prompt injection. AI work cannot begin before the portfolio and decision foundations exist.
