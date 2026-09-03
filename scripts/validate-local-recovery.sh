#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required for the local recovery drill." >&2
  exit 2
}

project_name="hawkfund-recovery-${PPID}"
backup_dir="$(mktemp -d)"
source_db="hawkfund"
restore_db="hawkfund_restore"
export POSTGRES_PORT="55432"

cleanup() {
  docker compose -p "$project_name" down --volumes
  find "$backup_dir" -type f -delete
  rmdir "$backup_dir"
}
trap cleanup EXIT

docker compose -p "$project_name" up -d postgres redis
docker compose -p "$project_name" run --rm api alembic -c alembic.ini upgrade head
docker compose -p "$project_name" run --rm api python /db/fixtures/load.py

docker compose -p "$project_name" exec -T postgres \
  pg_dump -U hawkfund --format=custom "$source_db" >"$backup_dir/hawkfund.dump"
docker compose -p "$project_name" exec -T postgres createdb -U hawkfund "$restore_db"
docker compose -p "$project_name" exec -T postgres \
  pg_restore -U hawkfund --dbname="$restore_db" --exit-on-error <"$backup_dir/hawkfund.dump"

source_fingerprint="$(docker compose -p "$project_name" exec -T postgres psql -U hawkfund -d "$source_db" -Atc \
  "select (select count(*) from funds)||':'||(select count(*) from users)||':'||(select count(*) from instruments)||':'||(select count(*) from import_batches)")"
restore_fingerprint="$(docker compose -p "$project_name" exec -T postgres psql -U hawkfund -d "$restore_db" -Atc \
  "select (select count(*) from funds)||':'||(select count(*) from users)||':'||(select count(*) from instruments)||':'||(select count(*) from import_batches)")"

[[ "$source_fingerprint" == "$restore_fingerprint" ]]
echo "Local backup/restore drill passed with fingerprint $restore_fingerprint."
