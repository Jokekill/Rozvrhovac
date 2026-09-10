#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for the database..."
python - <<'PY'
import os, time
import sqlalchemy
url = os.environ.get("DATABASE_URL", "")
for attempt in range(60):
    try:
        sqlalchemy.create_engine(url).connect().close()
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Database did not become available")
PY

alembic upgrade head
if [ "${SEED_DEMO:-false}" = "true" ]; then
  python manage.py seed-demo || true
fi
exec "$@"
