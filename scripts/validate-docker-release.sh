#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required for release acceptance." >&2
  exit 2
}
docker compose version >/dev/null
docker compose config --quiet

api_image="hawkfund-api:release-validation"
web_image="hawkfund-web:release-validation"
docker build --target production -t "$api_image" -f apps/api/Dockerfile .
docker build --target production -t "$web_image" -f apps/web/Dockerfile .

for image_name in "$api_image" "$web_image"; do
  image_user="$(docker image inspect --format '{{.Config.User}}' "$image_name")"
  if [[ -z "$image_user" || "$image_user" == "0" || "$image_user" == "root" ]]; then
    echo "$image_name does not declare a non-root runtime user." >&2
    exit 1
  fi
done

docker compose up -d --build
cleanup() {
  docker compose down
}
trap cleanup EXIT

for attempt in {1..60}; do
  if curl --fail --silent http://127.0.0.1:${API_PORT:-8000}/health/ready >/dev/null && \
    curl --fail --silent http://127.0.0.1:${WEB_PORT:-3000} >/dev/null; then
    break
  fi
  if [[ "$attempt" == "60" ]]; then
    docker compose ps
    docker compose logs --no-color --tail=200
    exit 1
  fi
  sleep 2
done

docker compose run --rm api alembic -c alembic.ini upgrade head
docker compose run --rm api python /db/fixtures/load.py
docker compose run --rm api python /db/fixtures/load.py
docker compose exec -T redis redis-cli ping | grep -qx PONG

before_restart="$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-hawkfund}" -d "${POSTGRES_DB:-hawkfund}" -Atc 'select count(*) from funds')"
docker compose restart postgres
for attempt in {1..30}; do
  if docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-hawkfund}" -d "${POSTGRES_DB:-hawkfund}" >/dev/null; then
    break
  fi
  [[ "$attempt" != "30" ]] || exit 1
  sleep 2
done
after_restart="$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-hawkfund}" -d "${POSTGRES_DB:-hawkfund}" -Atc 'select count(*) from funds')"
[[ "$before_restart" == "$after_restart" && "$after_restart" -gt 0 ]]

docker compose ps
echo "Docker release acceptance passed. Persistent volumes were preserved."
