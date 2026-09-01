# ADR 0001: Use a modular monolith

Status: Accepted

## Context

HawkFundOS needs clear domain boundaries but will initially be built and operated by a small team. Distributed services would add deployment, consistency, tracing, and local-development costs before those costs solve a measured problem.

## Decision

Use one Next.js web application, one FastAPI application, one background-worker process when Phase 1 requires it, and one PostgreSQL database. Organize backend code by domain module and enforce boundaries in code and tests.

## Alternatives

- Microservices: rejected because the initial scale and team do not justify operational complexity.
- Single full-stack Next.js application: rejected because Python is the intended analytics environment and should own domain calculations.

## Consequences

Local setup and transactions remain simple. Modules can be extracted later, but disciplined interfaces are required to prevent an unstructured monolith.
