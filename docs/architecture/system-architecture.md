# HawkFundOS system architecture

```mermaid
flowchart LR
    U[Analyst / Manager / Advisor] -->|HTTPS| ALB[Application Load Balancer]
    ALB --> WEB[Next.js web service]
    ALB --> API[FastAPI modular monolith]

    subgraph TRUST[Private application trust boundary]
        API --> AUTH[Authorization and governance]
        API --> LEDGER[Append-only transaction ledger]
        API --> MARKET[Market-data ingestion]
        API --> CALC[Deterministic portfolio, valuation, analytics, risk and scenarios]
        API --> AI[Read-only AI orchestration]
        AUTH --> AUDIT[Immutable audit events]
        LEDGER --> PG[(PostgreSQL system of record)]
        MARKET --> PG
        CALC --> PG
        AUTH --> PG
        AUDIT --> PG
        API --> REDIS[(Redis cache)]
        AI --> TOOLS[Typed, fund-scoped read-only tools]
        TOOLS --> CALC
        TOOLS --> PG
    end

    MARKET -->|typed provider adapter| VENDOR[Market-data provider]
    AI -->|tool requests and grounded evidence only| MODEL[AI model provider]
    SM[Secrets Manager] --> API
    SM --> WEB
    CW[CloudWatch logs, metrics and alarms] <-->|telemetry| API
    CW <-->|telemetry| WEB

    subgraph EVIDENCE[Decision evidence chain]
        TX[Transaction] --> RECON[Point-in-time reconstruction]
        PRICE[Provenanced price] --> VALUE[Historical valuation]
        RECON --> VALUE
        VALUE --> RISK[Exposure and risk]
        RISK --> SCENARIO[Before/after scenario]
        RISK --> BREACH[Versioned policy evaluation]
        SCENARIO --> PROPOSAL[Versioned investment proposal]
        BREACH --> PROPOSAL
        PROPOSAL --> EXPLAIN[Grounded AI explanation]
        EXPLAIN --> TRACE[Source citations and audit trail]
    end
```

## Architectural invariants

- PostgreSQL, not Redis or the AI provider, is the authoritative record.
- Transactions, source observations, proposal history, and audit events are append-oriented.
- Every point-in-time calculation uses explicit cutoffs, versions, and canonical input hashes.
- The model cannot mutate the portfolio or calculate financial metrics; it can only invoke the
  allowlisted, authorized read-only tools and explain returned evidence.
- Only the load balancer is public in AWS. ECS tasks, RDS, and ElastiCache remain in private subnets.
