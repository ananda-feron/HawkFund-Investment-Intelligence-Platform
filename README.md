# HawkFundOS

Portfolio Intelligence & Risk Platform for the SUNY New Paltz Hawk Fund.

This repository is currently at **Phase 0: infrastructure baseline**. It contains no portfolio, risk, research, scenario, decision, or AI features.

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

- one SUNY New Paltz Hawk Fund record;
- three roles and one development user per role;
- four reference instruments: AAPL, MSFT, NVDA, and SPY.

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

## Phase boundary

Phase 0 proves that a clean checkout starts, migrates, seeds, and passes the same checks used in CI. Business-domain implementation begins in Phase 1 only.
