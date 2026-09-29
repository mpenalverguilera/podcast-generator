#!/bin/sh
# Runs on every container start: migrate, seed, then the API (D-73).
# Every step is idempotent: seed-users skips existing users, and
# seed-metrics replaces only its own @synthetic.invalid rows.
set -e

alembic upgrade head
python -m app.cli seed-users
if [ "${SEED_METRICS:-1}" = "1" ]; then
  python -m app.cli seed-metrics
fi

exec "$@"
