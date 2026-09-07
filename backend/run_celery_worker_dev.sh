#!/usr/bin/env bash
# Worker Celery con recarga al cambiar .py (compose: worker-agro / worker-fire).
# Uso:
#   ./run_celery_worker_dev.sh          # cola agro (default)
#   ./run_celery_worker_dev.sh fire     # cola fire
#   CELERY_QUEUE=fire ./run_celery_worker_dev.sh
#
# Antes: pip install -r requirements.txt (incluye watchfiles y celery).
# Variables típicas en local (ajusta a tu máquina; puedes ponerlas en .env en la raíz del repo):
#   export DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5433/xeniamap
#   export REDIS_URL=redis://localhost:6379/0
#   export STORAGE_PATH=/ruta/al/repo/data/storage

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
  set +a
fi

# Sin Docker, STORAGE_PATH suele ser la carpeta data/storage del repo (misma que compose).
export STORAGE_PATH="${STORAGE_PATH:-$REPO_ROOT/data/storage}"
mkdir -p "$STORAGE_PATH"

QUEUE="${1:-${CELERY_QUEUE:-agro}}"
case "$QUEUE" in
  agro|fire) ;;
  *)
    echo "Cola inválida: $QUEUE (use agro|fire)" >&2
    exit 2
    ;;
esac

if ! python3 -c "import watchfiles, celery" 2>/dev/null; then
  echo "Instalando dependencias (pip install -r requirements.txt)…" >&2
  python3 -m pip install -r "$SCRIPT_DIR/requirements.txt"
fi

exec watchfiles --filter python \
  "celery -A app.tasks.celery_app.celery_app worker -Q ${QUEUE} --loglevel=info --concurrency=1 --max-tasks-per-child=2" \
  .
