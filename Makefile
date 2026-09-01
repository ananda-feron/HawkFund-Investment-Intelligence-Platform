.PHONY: bootstrap up down logs migrate migrate-down fixtures check check-api check-web clean-volumes

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

check: check-api check-web

check-api:
	cd apps/api && ruff check app tests ../../db && ruff format --check app tests ../../db
	cd apps/api && mypy app
	cd apps/api && pytest

check-web:
	npm run lint:web
	npm run typecheck:web
	npm run test:web

clean-volumes:
	docker compose down --volumes
