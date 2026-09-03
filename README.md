# HawkFundOS

Portfolio Intelligence & Risk Platform for the SUNY New Paltz Hawk Fund.

Phase 0 infrastructure, Phase 1's portfolio system of record, and Phase 2 market valuation are
complete. Phase 3 adds portfolio analytics and risk controls. Phase 4 adds non-mutating,
deterministic scenarios and before/after stress comparisons. Phase 5 adds controlled investment
proposals, fund-scoped authorization, liquidity policies, and immutable approval evidence. Research,
trade execution, and write-capable AI remain unimplemented. Phase 6 adds a governed, read-only AI
intelligence layer over deterministic portfolio services. Phase 7 adds production images, AWS
infrastructure-as-code, deployment gates, observability, recovery guidance, and security controls.

## Prerequisites

- Docker Desktop with Docker Compose v2
- `make`
- Node.js 22+ and Python 3.12+ only if running checks outside containers

## Start from a clean clone

```bash
cp .env.example .env
make bootstrap
```

`make bootstrap` builds and starts Next.js, FastAPI, PostgreSQL, and Redis; applies every database migration; and loads deterministic fixtures.

Open:

- Web: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/health/live>
- API readiness: <http://localhost:8000/health/ready>

Expected homepage text: `HawkFundOS is running.`

## Common commands

```bash
make up             # start the stack in the foreground
make down           # stop services and retain data
make logs           # follow service logs
make migrate        # apply migrations
make migrate-down   # roll back one migration
make fixtures       # reload idempotent fixtures
make check          # run backend and frontend checks locally
make clean-volumes  # delete local Docker data volumes
```

`make clean-volumes` removes the local PostgreSQL and Redis Docker volumes. Use it only when intentionally resetting development data.

## Deterministic fixtures

The Phase 0 fixture loader creates:

- one SUNY New Paltz Hawk Fund record and one primary account;
- three roles and one development user per role;
- four reference instruments with primary ticker identifiers and classifications;
- one versioned Hawk Fund base risk policy with technology, position concentration, cash, and
  portfolio-liquidity limits;
- three versioned scenario definitions: security selloff, illustrative historical crisis proxy,
  and rates/growth-factor stress.

All IDs and timestamps are stable, and rerunning the fixture loader is safe. No position or transaction data is created.

## Run checks without Docker

```bash
npm ci
npm run lint:web
npm run typecheck:web
npm run test:web

python3.12 -m venv .venv
.venv/bin/pip install -r apps/api/requirements-dev.txt
cd apps/api
../../.venv/bin/ruff check app tests ../../db
../../.venv/bin/ruff format --check app tests ../../db
../../.venv/bin/mypy app
../../.venv/bin/pytest
```

The liveness test does not require PostgreSQL or Redis. Readiness intentionally fails unless both dependencies are reachable.

## Repository map

```text
apps/web/              Next.js user interface
apps/api/              FastAPI service
db/migrations/         Alembic migrations
db/fixtures/           deterministic bootstrap data
docs/architecture/     architecture decision records
infra/docker/          container documentation and future overrides
.github/workflows/     continuous integration
```

## Current phase boundary

Phase 7 supplies hardened non-root production images and Terraform for an HTTPS ALB, private ECS
Fargate services, encrypted RDS PostgreSQL, encrypted ElastiCache, Secrets Manager, ECR, CloudWatch,
autoscaling, and alarms. CI validates code, migrations, Terraform, dependencies, containers, and
CodeQL. Manual deployments use a protected GitHub environment, short-lived AWS OIDC credentials,
immutable image tags, migration-before-rollout ordering, and ECS deployment rollback.

Infrastructure is not provisioned automatically by cloning the repository. An AWS account,
certificate/domain, remote Terraform state, GitHub environment approval rules, and a bootstrapped
least-privilege deployment role are required. See `docs/operations/production-runbook.md`.

## Release validation

Release-candidate validation is feature-frozen and documented in
[`docs/release-validation.md`](docs/release-validation.md). Run the deterministic cross-domain test
with `make golden-path`; on a Docker-enabled host, also run `make docker-acceptance` and
`make recovery-drill`. The final trust boundaries and evidence flow are shown in
[`docs/architecture/system-architecture.md`](docs/architecture/system-architecture.md).
