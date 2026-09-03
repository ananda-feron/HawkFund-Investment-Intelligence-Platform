.PHONY: bootstrap up down logs migrate migrate-down fixtures check check-api check-web check-infra perf-smoke clean-volumes

bootstrap:
	docker compose up -d --build
	docker compose run --rm api alembic -c alembic.ini upgrade head
	docker compose run --rm api python /db/fixtures/load.py

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose run --rm api alembic -c alembic.ini upgrade head

migrate-down:
	docker compose run --rm api alembic -c alembic.ini downgrade -1

fixtures:
	docker compose run --rm api python /db/fixtures/load.py

check: check-api check-web check-infra

check-api:
	cd apps/api && ruff check app tests ../../db && ruff format --check app tests ../../db
	cd apps/api && mypy app
	cd apps/api && pytest

check-web:
	npm run lint:web
	npm run typecheck:web
	npm run test:web

check-infra:
	terraform fmt -check -recursive infra/aws
	cd infra/aws && terraform init -backend=false -input=false && terraform validate

perf-smoke:
	python3 tests/performance/health_smoke.py

clean-volumes:
	docker compose down --volumes
